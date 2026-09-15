"""Inventory metadata and CSV preview helpers."""

from __future__ import annotations

import csv
import io
import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from backend.app.config import inventory_csv_dir
from backend.app.db.database import get_connection
from backend.app.db.users import get_user_by_idx

logger = logging.getLogger(__name__)

_INVALID_IDENT = re.compile(r"[^0-9a-zA-Z_]+")
_PG_IDENT = re.compile(r"^[a-z][a-z0-9_]*$")
_TABLE_NAME_PREFIX = "inventory_"
_DISPLAY_NAME_MAX = 100
_DESCRIPTION_MAX = 200
_TABLE_NAME_MAX = 50
_ORIGIN_CSV_MAX = 100
_PREVIEW_DEFAULT_LIMIT = 50
_PREVIEW_MAX_LIMIT = 200
_COLUMN_TYPE = "TEXT"  # unified type until UI exposes per-column types


@dataclass(frozen=True)
class InventoryRecord:
    idx: int
    table_name: str
    display_name: str
    description: str
    created_by: int
    origin_csv: str
    created_by_username: str = ""


def ensure_inventory_table(connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory (
            idx SERIAL PRIMARY KEY,
            table_name VARCHAR(50) NOT NULL DEFAULT '',
            display_name VARCHAR(100) NOT NULL,
            description VARCHAR(200) NOT NULL DEFAULT '',
            created_by INTEGER NOT NULL DEFAULT 1,
            origin_csv VARCHAR(100) NOT NULL DEFAULT ''
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS ix_inventory_display_name ON inventory (display_name)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS ix_inventory_created_by ON inventory (created_by)"
    )


def _row_to_record(row, *, username: str = "") -> InventoryRecord:
    return InventoryRecord(
        idx=int(row["idx"] or 0),
        table_name=str(row["table_name"] or ""),
        display_name=str(row["display_name"] or ""),
        description=str(row["description"] or ""),
        created_by=int(row["created_by"] or 1) or 1,
        origin_csv=str(row["origin_csv"] or ""),
        created_by_username=username,
    )


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
    # Keep room for postgres identifier limit (63) — already capped at 50.
    return text


def quote_ident(name: str) -> str:
    """Quote a validated identifier for DDL (double-quote, escape internals)."""
    if not _PG_IDENT.match(name):
        raise ValueError(f"잘못된 식별자입니다: {name}")
    return '"' + name.replace('"', '""') + '"'


def table_exists(connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT 1 AS ok
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def get_inventory_by_table_name(
    database_path: str | Path,
    table_name: str,
) -> InventoryRecord | None:
    with get_connection(database_path) as connection:
        ensure_inventory_table(connection)
        row = connection.execute(
            """
            SELECT idx, table_name, display_name, description, created_by, origin_csv
            FROM inventory
            WHERE table_name = ?
            """,
            (table_name,),
        ).fetchone()
    if row is None:
        return None
    user = get_user_by_idx(database_path, int(row["created_by"] or 0))
    username = (user.username or user.userid) if user is not None else ""
    return _row_to_record(row, username=username)


def create_inventory_data_table(connection, table_name: str, columns: list[str]) -> None:
    if not columns:
        raise ValueError("테이블 컬럼이 없습니다.")
    for col in columns:
        if not _PG_IDENT.match(col):
            raise ValueError(f"잘못된 컬럼명입니다: {col}")
    quoted_table = quote_ident(table_name)
    col_defs = ", ".join(
        f"{quote_ident(col)} {_COLUMN_TYPE} NOT NULL DEFAULT ''" for col in columns
    )
    connection.execute(
        f"""
        CREATE TABLE {quoted_table} (
            idx SERIAL PRIMARY KEY,
            {col_defs}
        )
        """
    )


def drop_inventory_data_table(connection, table_name: str) -> None:
    validated = validate_inventory_table_name(table_name)
    connection.execute(f"DROP TABLE IF EXISTS {quote_ident(validated)}")


def insert_csv_rows(
    connection,
    table_name: str,
    columns: list[str],
    rows: list[dict[str, str]],
) -> int:
    if not rows:
        return 0
    quoted_table = quote_ident(table_name)
    quoted_cols = ", ".join(quote_ident(col) for col in columns)
    placeholders = ", ".join(["?"] * len(columns))
    sql = f"INSERT INTO {quoted_table} ({quoted_cols}) VALUES ({placeholders})"
    values = [tuple(row.get(col, "") or "" for col in columns) for row in rows]
    connection.executemany(sql, values)
    return len(values)


def replace_inventory_data_rows(
    connection,
    table_name: str,
    columns: list[str],
    rows: list[dict[str, str]],
) -> int:
    quoted_table = quote_ident(table_name)
    connection.execute(f"TRUNCATE TABLE {quoted_table} RESTART IDENTITY")
    return insert_csv_rows(connection, table_name, columns, rows)


def load_csv_file_rows(filename: str) -> tuple[list[str], list[dict[str, str]]]:
    path = resolve_inventory_csv_path(filename)
    columns, _labels, rows = validate_and_parse_csv(path.read_bytes())
    return columns, rows


def validate_and_parse_csv(
    content: bytes | str,
    *,
    encoding: str = "utf-8-sig",
) -> tuple[list[str], list[dict[str, str]], list[str]]:
    """Validate CSV and return (normalized_columns, original_header_labels, rows as dicts).

    Raises ``ValueError`` when the CSV is invalid.
    """
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


def save_inventory_csv(content: bytes, *, original_filename: str) -> str:
    """Save CSV under inventory/csv and return the stored basename."""
    original = Path(original_filename or "upload.csv").name.strip() or "upload.csv"
    if not original.lower().endswith(".csv"):
        original = f"{original}.csv"
    stem = Path(original).stem
    stem = re.sub(r"[^\w\-]+", "_", stem, flags=re.UNICODE).strip("_") or "upload"
    stored = f"{stem}_{uuid.uuid4().hex[:10]}.csv"[:_ORIGIN_CSV_MAX]
    directory = inventory_csv_dir()
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


def list_inventories(database_path: str | Path) -> list[InventoryRecord]:
    with get_connection(database_path) as connection:
        ensure_inventory_table(connection)
        rows = connection.execute(
            """
            SELECT idx, table_name, display_name, description, created_by, origin_csv
            FROM inventory
            ORDER BY idx DESC
            """
        ).fetchall()
    records: list[InventoryRecord] = []
    for row in rows:
        user = get_user_by_idx(database_path, int(row["created_by"] or 0))
        username = (user.username or user.userid) if user is not None else ""
        records.append(_row_to_record(row, username=username))
    return records


def get_inventory_by_idx(database_path: str | Path, idx: int) -> InventoryRecord | None:
    with get_connection(database_path) as connection:
        ensure_inventory_table(connection)
        row = connection.execute(
            """
            SELECT idx, table_name, display_name, description, created_by, origin_csv
            FROM inventory
            WHERE idx = ?
            """,
            (int(idx),),
        ).fetchone()
    if row is None:
        return None
    user = get_user_by_idx(database_path, int(row["created_by"] or 0))
    username = (user.username or user.userid) if user is not None else ""
    return _row_to_record(row, username=username)


def create_inventory(
    database_path: str | Path,
    *,
    display_name: str,
    description: str,
    created_by: int,
    origin_csv: str,
    table_name: str = "",
) -> InventoryRecord:
    name = (display_name or "").strip()
    if not name:
        raise ValueError("인벤토리 이름을 입력하세요.")
    if len(name) > _DISPLAY_NAME_MAX:
        raise ValueError(f"인벤토리 이름은 {_DISPLAY_NAME_MAX}자를 넘을 수 없습니다.")
    desc = (description or "").strip()[:_DESCRIPTION_MAX]
    csv_name = Path((origin_csv or "").strip()).name
    if not csv_name:
        raise ValueError("원본 CSV 파일명이 필요합니다.")
    columns, rows = load_csv_file_rows(csv_name)
    table = validate_inventory_table_name(table_name or "")
    owner = int(created_by or 0) or 1

    if get_inventory_by_table_name(database_path, table) is not None:
        raise ValueError(f"이미 등록된 인벤토리 테이블 명입니다: {table}")

    with get_connection(database_path) as connection:
        ensure_inventory_table(connection)
        if table_exists(connection, table):
            raise ValueError(f"이미 존재하는 DB 테이블입니다: {table}")
        create_inventory_data_table(connection, table, columns)
        try:
            insert_csv_rows(connection, table, columns, rows)
            row = connection.execute(
                """
                INSERT INTO inventory (
                    table_name, display_name, description, created_by, origin_csv
                )
                VALUES (?, ?, ?, ?, ?)
                RETURNING idx
                """,
                (table, name, desc, owner, csv_name[:_ORIGIN_CSV_MAX]),
            ).fetchone()
            idx = int(row["idx"])
        except Exception:
            drop_inventory_data_table(connection, table)
            raise

    record = get_inventory_by_idx(database_path, idx)
    if record is None:
        raise ValueError("인벤토리 저장 후 조회에 실패했습니다.")
    return record


def update_inventory(
    database_path: str | Path,
    idx: int,
    *,
    display_name: str,
    description: str,
    origin_csv: str | None = None,
) -> InventoryRecord:
    existing = get_inventory_by_idx(database_path, idx)
    if existing is None:
        raise ValueError("인벤토리를 찾을 수 없습니다.")

    name = (display_name or "").strip()
    if not name:
        raise ValueError("인벤토리 이름을 입력하세요.")
    if len(name) > _DISPLAY_NAME_MAX:
        raise ValueError(f"인벤토리 이름은 {_DISPLAY_NAME_MAX}자를 넘을 수 없습니다.")
    desc = (description or "").strip()[:_DESCRIPTION_MAX]

    next_csv = existing.origin_csv
    previous_csv = existing.origin_csv
    replace_rows: tuple[list[str], list[dict[str, str]]] | None = None
    if origin_csv is not None:
        csv_name = Path((origin_csv or "").strip()).name
        if not csv_name:
            raise ValueError("원본 CSV 파일명이 필요합니다.")
        resolve_inventory_csv_path(csv_name)
        if csv_name != existing.origin_csv:
            if not existing.origin_csv:
                raise ValueError("기존 origin_csv가 없어 컬럼을 비교할 수 없습니다.")
            compare_csv_columns(existing.origin_csv, csv_name)
            replace_rows = load_csv_file_rows(csv_name)
            next_csv = csv_name[:_ORIGIN_CSV_MAX]

    with get_connection(database_path) as connection:
        ensure_inventory_table(connection)
        if replace_rows is not None:
            if not existing.table_name:
                raise ValueError("연결된 데이터 테이블이 없습니다.")
            columns, rows = replace_rows
            replace_inventory_data_rows(connection, existing.table_name, columns, rows)
        connection.execute(
            """
            UPDATE inventory
            SET display_name = ?, description = ?, origin_csv = ?
            WHERE idx = ?
            """,
            (name, desc, next_csv, int(idx)),
        )

    if next_csv != previous_csv and previous_csv:
        try:
            old_path = resolve_inventory_csv_path(previous_csv)
            if old_path.name != next_csv:
                old_path.unlink(missing_ok=True)
        except (ValueError, FileNotFoundError, OSError):
            logger.warning(
                "inventory csv replace cleanup skipped idx=%s file=%s",
                idx,
                previous_csv,
            )

    record = get_inventory_by_idx(database_path, idx)
    if record is None:
        raise ValueError("인벤토리 수정 후 조회에 실패했습니다.")
    return record


def delete_inventory(database_path: str | Path, idx: int) -> bool:
    existing = get_inventory_by_idx(database_path, idx)
    if existing is None:
        return False
    if existing.table_name:
        from backend.app.db.inventory_api import delete_inventory_apis_by_table

        delete_inventory_apis_by_table(database_path, existing.table_name)
    with get_connection(database_path) as connection:
        ensure_inventory_table(connection)
        connection.execute("DELETE FROM inventory WHERE idx = ?", (int(idx),))
        if existing.table_name:
            try:
                drop_inventory_data_table(connection, existing.table_name)
            except ValueError:
                logger.warning(
                    "inventory data table drop skipped idx=%s table=%s",
                    idx,
                    existing.table_name,
                )
    if existing.origin_csv:
        try:
            path = resolve_inventory_csv_path(existing.origin_csv)
            path.unlink(missing_ok=True)
        except (ValueError, FileNotFoundError, OSError):
            logger.warning("inventory csv cleanup skipped idx=%s file=%s", idx, existing.origin_csv)
    return True
