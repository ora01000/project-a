"""Inventory CSV helpers and table-name validation (metadata is remote)."""

from __future__ import annotations

import csv
import io
import logging
import re
import uuid
from pathlib import Path

from backend.app.config import inventory_csv_dir

logger = logging.getLogger(__name__)

_INVALID_IDENT = re.compile(r"[^0-9a-zA-Z_]+")
_PG_IDENT = re.compile(r"^[a-z][a-z0-9_]*$")
_TABLE_NAME_PREFIX = "inventory_"
_TEMP_TABLE_PREFIX = "temp_"
_TABLE_NAME_MAX = 50
_ORIGIN_CSV_MAX = 100
_PREVIEW_DEFAULT_LIMIT = 50
_PREVIEW_MAX_LIMIT = 200


def ensure_inventory_table(connection) -> None:
    """Drop legacy local inventory tables (metadata now lives in remote API)."""
    connection.execute("DROP TABLE IF EXISTS inventory_api CASCADE")
    connection.execute("DROP TABLE IF EXISTS inventory CASCADE")


def normalize_csv_column_name(raw: str, *, index: int) -> str:
    text = (raw or "").strip()
    text = text.replace(" ", "_")
    text = _INVALID_IDENT.sub("_", text)
    text = re.sub(r"_+", "_", text).strip("_").lower()
    if not text:
        text = f"col_{index + 1}"
    if text[0].isdigit():
        text = f"c_{text}"
    return text[:60]


def normalize_table_name(raw: str) -> str:
    """Normalize user input toward a postgres-safe ``inventory_*`` name."""
    text = (raw or "").strip().lower()
    text = text.replace("-", "_").replace(" ", "_")
    text = _INVALID_IDENT.sub("_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        text = "inventory_"
    if not text.startswith(_TABLE_NAME_PREFIX):
        text = f"{_TABLE_NAME_PREFIX}{text}"
    return text[:_TABLE_NAME_MAX]


def validate_inventory_table_name(raw: str) -> str:
    """Validate postgres identifier rules and require ``inventory_`` prefix."""
    text = (raw or "").strip().lower()
    if not text:
        raise ValueError("인벤토리 테이블 명을 입력하세요.")
    if len(text) > _TABLE_NAME_MAX:
        raise ValueError(f"인벤토리 테이블 명은 {_TABLE_NAME_MAX}자를 넘을 수 없습니다.")
    if not text.startswith(_TABLE_NAME_PREFIX):
        raise ValueError(f'테이블 명은 반드시 "{_TABLE_NAME_PREFIX}"로 시작해야 합니다.')
    if text == _TABLE_NAME_PREFIX:
        raise ValueError(f'"{_TABLE_NAME_PREFIX}" 뒤에 식별자를 추가하세요.')
    if not _PG_IDENT.match(text):
        raise ValueError(
            "테이블 명은 소문자·숫자·밑줄만 사용할 수 있으며, 숫자로 시작할 수 없습니다."
        )
    return text


def temp_table_name_for(table_name: str) -> str:
    """Build ``temp_{inventory_*}`` name used before save."""
    final_name = validate_inventory_table_name(table_name)
    temp_name = f"{_TEMP_TABLE_PREFIX}{final_name}"
    if len(temp_name) > _TABLE_NAME_MAX:
        raise ValueError(
            f"임시 테이블명({temp_name})이 {_TABLE_NAME_MAX}자를 초과합니다. "
            "테이블 명을 더 짧게 입력하세요."
        )
    if not _PG_IDENT.match(temp_name):
        raise ValueError("임시 테이블 명이 올바르지 않습니다.")
    return temp_name


def validate_preview_table_name(raw: str) -> str:
    """Allow final ``inventory_*`` or temporary ``temp_inventory_*`` names."""
    text = (raw or "").strip().lower()
    if not text:
        raise ValueError("테이블 명을 입력하세요.")
    if len(text) > _TABLE_NAME_MAX:
        raise ValueError(f"테이블 명은 {_TABLE_NAME_MAX}자를 넘을 수 없습니다.")
    if not _PG_IDENT.match(text):
        raise ValueError(
            "테이블 명은 소문자·숫자·밑줄만 사용할 수 있으며, 숫자로 시작할 수 없습니다."
        )
    if text.startswith(_TEMP_TABLE_PREFIX):
        suffix = text[len(_TEMP_TABLE_PREFIX) :]
        validate_inventory_table_name(suffix)
        return text
    return validate_inventory_table_name(text)


def validate_and_parse_csv(
    content: bytes | str,
    *,
    encoding: str = "utf-8-sig",
) -> tuple[list[str], list[str], list[dict[str, str]]]:
    """Validate CSV and return (normalized_columns, original_header_labels, rows)."""
    if isinstance(content, bytes):
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            text = content.decode("cp949", errors="replace")
    else:
        text = content

    if not text.strip():
        raise ValueError("CSV 내용이 비어 있습니다.")

    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ValueError("CSV 헤더(첫 행)가 없습니다.") from exc

    labels = [(cell or "").strip() for cell in header]
    if not any(labels):
        raise ValueError("CSV 헤더가 비어 있습니다.")

    columns: list[str] = []
    seen: set[str] = set()
    for index, label in enumerate(labels):
        name = normalize_csv_column_name(label or f"col_{index + 1}", index=index)
        base = name
        suffix = 2
        while name in seen:
            name = f"{base}_{suffix}"[:60]
            suffix += 1
        seen.add(name)
        columns.append(name)

    rows: list[dict[str, str]] = []
    for row in reader:
        if not any((cell or "").strip() for cell in row):
            continue
        item: dict[str, str] = {}
        for index, col in enumerate(columns):
            item[col] = (row[index] if index < len(row) else "") or ""
        rows.append(item)

    if not rows:
        raise ValueError("데이터 행이 없습니다. 헤더 외 최소 1행이 필요합니다.")

    return columns, labels, rows


def rewrite_csv_with_normalized_headers(content: bytes | str) -> tuple[bytes, list[str], list[str]]:
    """Return UTF-8 CSV bytes whose header row uses normalized column names."""
    columns, labels, rows = validate_and_parse_csv(content)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(col, "") for col in columns])
    return buffer.getvalue().encode("utf-8"), columns, labels


def save_inventory_csv(
    content: bytes,
    *,
    original_filename: str,
    stored_filename: str | None = None,
) -> str:
    """Save CSV under inventory/csv and return the stored basename."""
    directory = inventory_csv_dir()
    if stored_filename:
        stored = Path(stored_filename.strip()).name
        if not stored.lower().endswith(".csv"):
            stored = f"{stored}.csv"
        stored = stored[:_ORIGIN_CSV_MAX]
        if not stored or stored in {".", ".."} or ".." in stored:
            raise ValueError("CSV 저장 파일명이 올바르지 않습니다.")
    else:
        original = Path(original_filename or "upload.csv").name.strip() or "upload.csv"
        if not original.lower().endswith(".csv"):
            original = f"{original}.csv"
        stem = Path(original).stem
        stem = re.sub(r"[^\w\-]+", "_", stem, flags=re.UNICODE).strip("_") or "upload"
        stored = f"{stem}_{uuid.uuid4().hex[:10]}.csv"[:_ORIGIN_CSV_MAX]
    path = (directory / stored).resolve()
    try:
        path.relative_to(directory.resolve())
    except ValueError as exc:
        raise ValueError("CSV 저장 경로가 올바르지 않습니다.") from exc
    path.write_bytes(content)
    return stored


def resolve_inventory_csv_path(filename: str) -> Path:
    name = Path((filename or "").strip()).name
    if not name or name != (filename or "").strip() or ".." in name:
        raise ValueError("CSV 파일명이 올바르지 않습니다.")
    directory = inventory_csv_dir()
    path = (directory / name).resolve()
    try:
        path.relative_to(directory.resolve())
    except ValueError as exc:
        raise ValueError("CSV 파일명이 올바르지 않습니다.") from exc
    if not path.is_file():
        raise FileNotFoundError(f"CSV 파일을 찾을 수 없습니다: {name}")
    return path


def preview_inventory_csv(
    filename: str,
    *,
    offset: int = 0,
    limit: int = _PREVIEW_DEFAULT_LIMIT,
) -> dict[str, object]:
    path = resolve_inventory_csv_path(filename)
    content = path.read_bytes()
    columns, labels, rows = validate_and_parse_csv(content)
    start = max(0, int(offset or 0))
    size = min(_PREVIEW_MAX_LIMIT, max(1, int(limit or _PREVIEW_DEFAULT_LIMIT)))
    slice_rows = rows[start : start + size]
    return {
        "filename": path.name,
        "columns": columns,
        "labels": labels,
        "rows": slice_rows,
        "offset": start,
        "limit": size,
        "total_rows": len(rows),
        "has_more": start + size < len(rows),
    }


def load_csv_columns(filename: str) -> list[str]:
    path = resolve_inventory_csv_path(filename)
    columns, _labels, _rows = validate_and_parse_csv(path.read_bytes())
    return columns


def assert_csv_columns_compatible(expected: list[str], actual: list[str]) -> None:
    """Raise ValueError when column count or normalized names differ."""
    if len(expected) != len(actual):
        raise ValueError(
            f"CSV 컬럼 개수가 일치하지 않습니다. "
            f"기존 {len(expected)}개, 업로드 {len(actual)}개"
        )
    if list(expected) != list(actual):
        raise ValueError(
            "정규화된 CSV 컬럼명이 기존과 일치하지 않습니다. "
            "origin_csv를 교체하려면 컬럼 개수와 이름이 동일해야 합니다."
        )


def compare_csv_columns(baseline_filename: str, candidate_filename: str) -> None:
    expected = load_csv_columns(baseline_filename)
    actual = load_csv_columns(candidate_filename)
    assert_csv_columns_compatible(expected, actual)
