"""Query table-type inventory CSV data via LLM-generated read-only SQL."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.db.database import get_connection
from backend.app.db.inventory_records import DB_TYPE_TABLE, list_stored_inventory
from backend.app.db.inventory_table_import import table_name_from_filename

logger = logging.getLogger(__name__)

MAX_SQL_RESULT_ROWS = 200
_FORBIDDEN_SQL_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|PRAGMA|"
    r"TRUNCATE|GRANT|REVOKE|VACUUM|REINDEX|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)
_SYSTEM_TABLES = {
    "users",
    "agents",
    "inventory",
    "jobs",
    "signup_notifications",
    "sqlite_master",
    "sqlite_sequence",
    "sqlite_schema",
}


@dataclass(frozen=True)
class InventoryTableSchema:
    inventory_idx: int
    inventory_name: str
    inventory_file: str
    table_name: str
    columns: list[str]


@dataclass(frozen=True)
class TableQueryResult:
    sql: str
    rationale: str
    columns: list[str]
    rows: list[dict[str, Any]]
    truncated: bool


def list_inventory_table_schemas(database_path: str | Path) -> list[InventoryTableSchema]:
    records = [
        record
        for record in list_stored_inventory(database_path)
        if record.effective_db_type == DB_TYPE_TABLE
    ]
    schemas: list[InventoryTableSchema] = []
    with get_connection(database_path) as connection:
        existing_tables = {
            str(row[0]).lower()
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for record in records:
            table_name = table_name_from_filename(record.inventory_file)
            if table_name.lower() not in existing_tables:
                logger.warning(
                    "Table inventory missing physical table idx=%s file=%s expected=%s",
                    record.idx,
                    record.inventory_file,
                    table_name,
                )
                continue
            column_rows = connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
            columns = [str(row["name"]) for row in column_rows]
            if not columns:
                continue
            schemas.append(
                InventoryTableSchema(
                    inventory_idx=record.idx,
                    inventory_name=record.inventory_name,
                    inventory_file=record.inventory_file,
                    table_name=table_name,
                    columns=columns,
                )
            )
    return schemas


def schemas_to_prompt_text(schemas: list[InventoryTableSchema]) -> str:
    blocks: list[str] = []
    for schema in schemas:
        columns = ", ".join(f'"{column}" VARCHAR(100)' for column in schema.columns)
        blocks.append(
            f"- inventory_name={schema.inventory_name}\n"
            f"  file={schema.inventory_file}\n"
            f"  table=\"{schema.table_name}\"\n"
            f"  columns=[{columns}]"
        )
    return "\n".join(blocks)


def extract_sql_from_llm_response(text: str) -> tuple[str, str]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:sql|json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped).strip()

    if stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
            sql = str(payload.get("sql") or "").strip()
            rationale = str(payload.get("rationale") or "").strip()
            if sql:
                return sql, rationale
        except json.JSONDecodeError:
            pass

    match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if match:
        try:
            payload = json.loads(match.group(0))
            sql = str(payload.get("sql") or "").strip()
            rationale = str(payload.get("rationale") or "").strip()
            if sql:
                return sql, rationale
        except json.JSONDecodeError:
            pass

    select_match = re.search(
        r"((?:WITH\b[\s\S]+)?SELECT\b[\s\S]+)",
        stripped,
        re.IGNORECASE,
    )
    if select_match:
        return select_match.group(1).strip().rstrip(";"), ""

    raise ValueError("LLM 응답에서 SQL을 추출하지 못했습니다.")


def validate_readonly_select_sql(sql: str, *, allowed_tables: set[str]) -> str:
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        raise ValueError("SQL이 비어 있습니다.")
    if ";" in cleaned:
        raise ValueError("한 개의 SQL 문만 허용됩니다.")
    if _FORBIDDEN_SQL_RE.search(cleaned):
        raise ValueError("SELECT(또는 WITH ... SELECT) 조회문만 허용됩니다.")

    upper = cleaned.lstrip().upper()
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        raise ValueError("SELECT(또는 WITH ... SELECT) 조회문만 허용됩니다.")

    allowed_lower = {name.lower() for name in allowed_tables}
    for system_table in _SYSTEM_TABLES:
        if system_table in allowed_lower:
            continue
        if re.search(rf'(?i)(?:FROM|JOIN)\s+"?{re.escape(system_table)}"?\b', cleaned):
            raise ValueError(f"시스템 테이블 접근은 허용되지 않습니다: {system_table}")

    if not any(
        re.search(rf'(?i)(?:FROM|JOIN)\s+"?{re.escape(table)}"?\b', cleaned)
        for table in allowed_tables
    ):
        raise ValueError("등록된 inventory table만 FROM/JOIN 할 수 있습니다.")

    if not re.search(r"(?i)\bLIMIT\b", cleaned):
        cleaned = f"{cleaned}\nLIMIT {MAX_SQL_RESULT_ROWS}"

    return cleaned


def execute_inventory_sql(
    database_path: str | Path,
    sql: str,
    *,
    allowed_tables: set[str],
) -> TableQueryResult:
    safe_sql = validate_readonly_select_sql(sql, allowed_tables=allowed_tables)
    with get_connection(database_path) as connection:
        cursor = connection.execute(safe_sql)
        column_names = [str(description[0]) for description in (cursor.description or [])]
        fetched = cursor.fetchmany(MAX_SQL_RESULT_ROWS + 1)

    truncated = len(fetched) > MAX_SQL_RESULT_ROWS
    rows_raw = fetched[:MAX_SQL_RESULT_ROWS]
    rows = [
        {column_names[index]: row[index] for index in range(len(column_names))}
        for row in rows_raw
    ]
    return TableQueryResult(
        sql=safe_sql,
        rationale="",
        columns=column_names,
        rows=rows,
        truncated=truncated,
    )


def format_table_query_result(result: TableQueryResult) -> str:
    lines = [
        f"실행 SQL:\n```sql\n{result.sql}\n```",
        f"조회 건수: {len(result.rows)}"
        + (" (결과가 잘렸습니다. LIMIT을 조정해 다시 질의하세요.)" if result.truncated else ""),
    ]
    if result.rationale:
        lines.append(f"선택 이유: {result.rationale}")

    if not result.rows:
        lines.append("조회 결과가 없습니다.")
        return "\n".join(lines)

    header = " | ".join(result.columns)
    separator = " | ".join("---" for _ in result.columns)
    lines.append("")
    lines.append(header)
    lines.append(separator)
    for row in result.rows:
        values = [str(row.get(column, "") or "") for column in result.columns]
        lines.append(" | ".join(values))
    return "\n".join(lines)
