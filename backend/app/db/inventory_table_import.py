"""Import CSV inventory files into dynamically created SQLite tables."""

from __future__ import annotations

import csv
import io
import logging
import re
from pathlib import Path

from backend.app.db.database import get_connection

logger = logging.getLogger(__name__)

COLUMN_VARCHAR_LENGTH = 100
_IDENTIFIER_RE = re.compile(r"[^a-zA-Z0-9_]+")
_RESERVED_TABLE_NAMES = {
    "users",
    "agents",
    "inventory",
    "jobs",
    "job_notifications",
    "signup_notifications",
    "k8s_cluster",
    "k8s_nodes",
    "k8s_namespaces",
    "k8s_deployments",
    "k8s_pvcs",
    "k8s_pods",
    "sqlite_master",
    "sqlite_sequence",
}


def sanitize_sql_identifier(raw: str, *, fallback_prefix: str = "col") -> str:
    cleaned = _IDENTIFIER_RE.sub("_", (raw or "").strip())
    cleaned = cleaned.strip("_")
    if not cleaned:
        cleaned = fallback_prefix
    if cleaned[0].isdigit():
        cleaned = f"{fallback_prefix}_{cleaned}"
    return cleaned[:64]


def table_name_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    table_name = sanitize_sql_identifier(stem, fallback_prefix="inventory")
    if table_name.lower() in _RESERVED_TABLE_NAMES:
        table_name = f"inv_{table_name}"
    return table_name


def drop_inventory_data_table(database_path: str | Path, table_name: str) -> None:
    safe_name = sanitize_sql_identifier(table_name, fallback_prefix="inventory")
    with get_connection(database_path) as connection:
        connection.execute(f'DROP TABLE IF EXISTS "{safe_name}"')
        connection.commit()
    logger.info("Dropped inventory data table %s", safe_name)


def import_csv_to_sqlite_table(
    database_path: str | Path,
    *,
    filename: str,
    content: bytes,
) -> tuple[str, int]:
    """Create/replace a SQLite table from CSV and insert rows.

    Returns (table_name, inserted_row_count).
    """
    table_name = table_name_from_filename(filename)
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV 헤더를 읽을 수 없습니다.")

    raw_headers = [header for header in reader.fieldnames if header and header.strip()]
    if not raw_headers:
        raise ValueError("CSV 헤더가 비어 있습니다.")

    columns: list[str] = []
    seen: set[str] = set()
    for index, header in enumerate(raw_headers):
        column = sanitize_sql_identifier(header, fallback_prefix=f"col_{index}")
        base = column
        suffix = 2
        while column.lower() in seen:
            column = f"{base}_{suffix}"
            suffix += 1
        seen.add(column.lower())
        columns.append(column)

    header_to_column = {
        header: columns[index] for index, header in enumerate(raw_headers)
    }

    column_defs = ", ".join(f'"{column}" VARCHAR({COLUMN_VARCHAR_LENGTH})' for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    quoted_columns = ", ".join(f'"{column}"' for column in columns)

    rows_to_insert: list[tuple[str, ...]] = []
    for row in reader:
        values: list[str] = []
        for header in raw_headers:
            raw_value = row.get(header)
            text_value = "" if raw_value is None else str(raw_value).strip()
            values.append(text_value[:COLUMN_VARCHAR_LENGTH])
        if not any(values):
            continue
        rows_to_insert.append(tuple(values))

    with get_connection(database_path) as connection:
        connection.execute(f'DROP TABLE IF EXISTS "{table_name}"')
        connection.execute(f'CREATE TABLE "{table_name}" ({column_defs})')
        if rows_to_insert:
            connection.executemany(
                f'INSERT INTO "{table_name}" ({quoted_columns}) VALUES ({placeholders})',
                rows_to_insert,
            )
        connection.commit()

    logger.info(
        "Imported CSV to SQLite table=%s columns=%s rows=%s headers=%s",
        table_name,
        len(columns),
        len(rows_to_insert),
        list(header_to_column.keys()),
    )
    return table_name, len(rows_to_insert)
