"""CRUD and query execution for inventory_api definitions."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from backend.app.db.database import get_connection
from backend.app.db.inventory import (
    _PG_IDENT,
    get_inventory_by_table_name,
    quote_ident,
    table_exists,
    validate_inventory_table_name,
)
from backend.app.db.users import get_user_by_idx

logger = logging.getLogger(__name__)

_API_NAME_MAX = 50
_DISPLAY_NAME_MAX = 100
_DESCRIPTION_MAX = 200
_API_FULLPATH_MAX = 255
_WHERE_EXP_MAX = 500
_SELECT_EXP_MAX = 500
_PARAM_COLUMNS_MAX = 500
_API_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_API_FULLPATH_PREFIX = "/api/inventory-data/"
_PARAM_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}", re.IGNORECASE)
_STRING_LITERAL = re.compile(r"'(?:''|[^'])*'")
_FORBIDDEN_SQL = re.compile(
    r"(;|--|/\*|\*/|\b(DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|EXECUTE)\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class InventoryApiRecord:
    idx: int
    api_name: str
    display_name: str
    description: str
    api_fullpath: str
    created_by: int
    table_name: str
    where_exp: str
    select_exp: str
    param_columns: str
    created_by_username: str = ""


def ensure_inventory_api_table(connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_api (
            idx SERIAL PRIMARY KEY,
            api_name VARCHAR(50) NOT NULL UNIQUE,
            display_name VARCHAR(100) NOT NULL,
            description VARCHAR(200) NOT NULL DEFAULT '',
            api_fullpath VARCHAR(255) NOT NULL UNIQUE,
            created_by INTEGER NOT NULL DEFAULT 1,
            table_name VARCHAR(50) NOT NULL,
            where_exp VARCHAR(500) NOT NULL DEFAULT '',
            select_exp VARCHAR(500) NOT NULL DEFAULT '',
            param_columns VARCHAR(500) NOT NULL DEFAULT ''
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS ix_inventory_api_table_name ON inventory_api (table_name)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS ix_inventory_api_created_by ON inventory_api (created_by)"
    )


def _row_to_record(row, *, username: str = "") -> InventoryApiRecord:
    return InventoryApiRecord(
        idx=int(row["idx"] or 0),
        api_name=str(row["api_name"] or ""),
        display_name=str(row["display_name"] or ""),
        description=str(row["description"] or ""),
        api_fullpath=str(row["api_fullpath"] or ""),
        created_by=int(row["created_by"] or 1) or 1,
        table_name=str(row["table_name"] or ""),
        where_exp=str(row["where_exp"] or ""),
        select_exp=str(row["select_exp"] or ""),
        param_columns=str(row["param_columns"] or ""),
        created_by_username=username,
    )


def build_api_fullpath(api_name: str) -> str:
    return f"{_API_FULLPATH_PREFIX}{api_name}"


def validate_api_name(raw: str) -> str:
    name = (raw or "").strip().lower()
    if not name:
        raise ValueError("API 이름을 입력하세요.")
    if len(name) > _API_NAME_MAX:
        raise ValueError(f"API 이름은 {_API_NAME_MAX}자를 넘을 수 없습니다.")
    if not _API_NAME_PATTERN.match(name):
        raise ValueError("API 이름은 영문 소문자·숫자·밑줄만 사용할 수 있습니다.")
    return name


def parse_param_columns(raw: str) -> list[str]:
    if not (raw or "").strip():
        return []
    columns: list[str] = []
    seen: set[str] = set()
    for part in (raw or "").split(","):
        col = part.strip().lower()
        if not col:
            continue
        if col in seen:
            continue
        if not _PG_IDENT.match(col):
            raise ValueError(f"잘못된 매개변수 컬럼명입니다: {col}")
        seen.add(col)
        columns.append(col)
    return columns


def list_table_columns(connection, table_name: str) -> list[str]:
    rows = connection.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = ?
          AND column_name <> 'idx'
        ORDER BY ordinal_position
        """,
        (table_name,),
    ).fetchall()
    return [str(row["column_name"]) for row in rows]


def validate_select_exp(select_exp: str, allowed_columns: set[str]) -> str:
    text = (select_exp or "").strip()
    if not text:
        raise ValueError("출력절(select)을 입력하세요.")
    if len(text) > _SELECT_EXP_MAX:
        raise ValueError(f"출력절은 {_SELECT_EXP_MAX}자를 넘을 수 없습니다.")
    if _FORBIDDEN_SQL.search(text):
        raise ValueError("출력절에 허용되지 않는 SQL 키워드가 포함되어 있습니다.")
    if text == "*":
        return text
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if not parts:
        raise ValueError("출력절(select)을 입력하세요.")
    for part in parts:
        token = part.split()[0].strip('"').lower()
        if token != "*" and token not in allowed_columns:
            raise ValueError(f"출력절에 존재하지 않는 컬럼이 있습니다: {token}")
    return text


def extract_param_placeholders(text: str) -> list[str]:
    """Return placeholder names in appearance order (``{col}`` syntax)."""
    return [match.group(1).lower() for match in _PARAM_PLACEHOLDER.finditer(text or "")]


def validate_where_exp(
    where_exp: str,
    allowed_columns: set[str],
    param_columns: list[str],
) -> str:
    text = (where_exp or "").strip()
    if not text:
        raise ValueError("조건절(where)을 입력하세요.")
    if len(text) > _WHERE_EXP_MAX:
        raise ValueError(f"조건절은 {_WHERE_EXP_MAX}자를 넘을 수 없습니다.")
    if _FORBIDDEN_SQL.search(text):
        raise ValueError("조건절에 허용되지 않는 SQL 키워드가 포함되어 있습니다.")
    if re.search(r":[a-zA-Z]", text):
        raise ValueError(
            "매개변수는 {column} 형식을 사용하세요. 예: asset_id like '%{asset_id}%'"
        )
    if re.search(r"\{[^{}]*\}", text) and not _PARAM_PLACEHOLDER.search(text):
        raise ValueError("잘못된 매개변수 형식입니다. {column} 형식만 사용할 수 있습니다.")

    param_set = set(param_columns)
    placeholders = extract_param_placeholders(text)
    if not placeholders:
        raise ValueError("조건절에 {column} 형식의 매개변수가 최소 1개 필요합니다.")
    for name in placeholders:
        if name not in param_set:
            raise ValueError(f"조건절의 매개변수 {{{name}}} 이(가) API 매개변수 목록에 없습니다.")
        if name not in allowed_columns:
            raise ValueError(f"조건절의 컬럼 {{{name}}} 이(가) 테이블에 없습니다.")

    # Strip string literals and placeholders before identifier whitelist checks.
    stripped = _STRING_LITERAL.sub(" ", text.lower())
    stripped = _PARAM_PLACEHOLDER.sub(" ", stripped)
    identifiers = re.findall(r"[a-z][a-z0-9_]*", stripped)
    allowed_tokens = allowed_columns | {
        "and",
        "or",
        "like",
        "ilike",
        "is",
        "not",
        "null",
        "true",
        "false",
        "in",
        "between",
    }
    for ident in identifiers:
        if ident not in allowed_tokens:
            raise ValueError(f"조건절에 허용되지 않는 식별자가 있습니다: {ident}")
    return text


def compile_where_clause(where_exp: str, param_columns: list[str]) -> tuple[str, list[str]]:
    """Convert ``{col}`` placeholders to bound ``?`` parameters.

    Supports placeholders inside string literals by rewriting them to
    concatenation so wildcards remain valid SQL, e.g.::

        asset_id like '%{asset_id}%'
        -> asset_id like '%' || ? || '%'
    """
    expected = set(param_columns)
    bind_order: list[str] = []

    def rewrite_string_literal(match: re.Match[str]) -> str:
        literal = match.group(0)
        inner = literal[1:-1]
        if not _PARAM_PLACEHOLDER.search(inner):
            return literal

        parts: list[str] = []
        last = 0
        for placeholder in _PARAM_PLACEHOLDER.finditer(inner):
            name = placeholder.group(1).lower()
            if name not in expected:
                raise ValueError(f"조건절의 매개변수 {{{name}}} 이(가) API 매개변수 목록에 없습니다.")
            prefix = inner[last : placeholder.start()]
            if prefix:
                parts.append("'" + prefix.replace("'", "''") + "'")
            bind_order.append(name)
            parts.append("?")
            last = placeholder.end()
        suffix = inner[last:]
        if suffix:
            parts.append("'" + suffix.replace("'", "''") + "'")
        if not parts:
            parts.append("''")
        return " || ".join(parts)

    sql = _STRING_LITERAL.sub(rewrite_string_literal, where_exp)

    def replace_bare_placeholder(match: re.Match[str]) -> str:
        name = match.group(1).lower()
        if name not in expected:
            raise ValueError(f"조건절의 매개변수 {{{name}}} 이(가) API 매개변수 목록에 없습니다.")
        bind_order.append(name)
        return "?"

    sql = _PARAM_PLACEHOLDER.sub(replace_bare_placeholder, sql)

    if not bind_order:
        raise ValueError("조건절에 {column} 형식의 매개변수가 최소 1개 필요합니다.")
    if set(bind_order) != expected:
        raise ValueError("조건절의 매개변수가 API 매개변수 목록과 일치하지 않습니다.")
    return sql, bind_order


def list_inventory_apis_by_table(
    database_path: str | Path,
    table_name: str,
) -> list[InventoryApiRecord]:
    table = validate_inventory_table_name(table_name)
    with get_connection(database_path) as connection:
        ensure_inventory_api_table(connection)
        rows = connection.execute(
            """
            SELECT idx, api_name, display_name, description, api_fullpath,
                   created_by, table_name, where_exp, select_exp, param_columns
            FROM inventory_api
            WHERE table_name = ?
            ORDER BY idx DESC
            """,
            (table,),
        ).fetchall()
    records: list[InventoryApiRecord] = []
    for row in rows:
        user = get_user_by_idx(database_path, int(row["created_by"] or 0))
        username = (user.username or user.userid) if user is not None else ""
        records.append(_row_to_record(row, username=username))
    return records


def get_inventory_api_by_idx(database_path: str | Path, idx: int) -> InventoryApiRecord | None:
    with get_connection(database_path) as connection:
        ensure_inventory_api_table(connection)
        row = connection.execute(
            """
            SELECT idx, api_name, display_name, description, api_fullpath,
                   created_by, table_name, where_exp, select_exp, param_columns
            FROM inventory_api
            WHERE idx = ?
            """,
            (int(idx),),
        ).fetchone()
    if row is None:
        return None
    user = get_user_by_idx(database_path, int(row["created_by"] or 0))
    username = (user.username or user.userid) if user is not None else ""
    return _row_to_record(row, username=username)


def get_inventory_api_by_name(database_path: str | Path, api_name: str) -> InventoryApiRecord | None:
    name = validate_api_name(api_name)
    with get_connection(database_path) as connection:
        ensure_inventory_api_table(connection)
        row = connection.execute(
            """
            SELECT idx, api_name, display_name, description, api_fullpath,
                   created_by, table_name, where_exp, select_exp, param_columns
            FROM inventory_api
            WHERE api_name = ?
            """,
            (name,),
        ).fetchone()
    if row is None:
        return None
    user = get_user_by_idx(database_path, int(row["created_by"] or 0))
    username = (user.username or user.userid) if user is not None else ""
    return _row_to_record(row, username=username)


def create_inventory_api(
    database_path: str | Path,
    *,
    api_name: str,
    display_name: str,
    description: str,
    table_name: str,
    where_exp: str,
    select_exp: str,
    param_columns: str,
    created_by: int,
) -> InventoryApiRecord:
    name = validate_api_name(api_name)
    label = (display_name or "").strip()
    if not label:
        raise ValueError("디스플레이 명을 입력하세요.")
    if len(label) > _DISPLAY_NAME_MAX:
        raise ValueError(f"디스플레이 명은 {_DISPLAY_NAME_MAX}자를 넘을 수 없습니다.")
    desc = (description or "").strip()[:_DESCRIPTION_MAX]
    table = validate_inventory_table_name(table_name)
    params = parse_param_columns(param_columns)
    if not params:
        raise ValueError("API 매개변수 컬럼을 1개 이상 선택하세요.")

    inventory = get_inventory_by_table_name(database_path, table)
    if inventory is None:
        raise ValueError("연결된 인벤토리를 찾을 수 없습니다.")

    with get_connection(database_path) as connection:
        ensure_inventory_api_table(connection)
        if not table_exists(connection, table):
            raise ValueError(f"데이터 테이블이 존재하지 않습니다: {table}")
        allowed = set(list_table_columns(connection, table))
        if not allowed:
            raise ValueError("테이블 컬럼 정보를 불러올 수 없습니다.")
        for col in params:
            if col not in allowed:
                raise ValueError(f"매개변수 컬럼이 테이블에 없습니다: {col}")
        validated_select = validate_select_exp(select_exp, allowed)
        validated_where = validate_where_exp(where_exp, allowed, params)
        fullpath = build_api_fullpath(name)
        if len(fullpath) > _API_FULLPATH_MAX:
            raise ValueError("API 경로가 너무 깁니다.")

        existing = connection.execute(
            "SELECT idx FROM inventory_api WHERE api_name = ? OR api_fullpath = ?",
            (name, fullpath),
        ).fetchone()
        if existing is not None:
            raise ValueError(f"이미 사용 중인 API 이름입니다: {name}")

        row = connection.execute(
            """
            INSERT INTO inventory_api (
                api_name, display_name, description, api_fullpath,
                created_by, table_name, where_exp, select_exp, param_columns
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING idx
            """,
            (
                name,
                label,
                desc,
                fullpath,
                int(created_by or 0) or 1,
                table,
                validated_where[:_WHERE_EXP_MAX],
                validated_select[:_SELECT_EXP_MAX],
                ",".join(params)[:_PARAM_COLUMNS_MAX],
            ),
        ).fetchone()
        idx = int(row["idx"])

    record = get_inventory_api_by_idx(database_path, idx)
    if record is None:
        raise ValueError("API 저장 후 조회에 실패했습니다.")
    return record


def update_inventory_api(
    database_path: str | Path,
    idx: int,
    *,
    api_name: str,
    display_name: str,
    description: str,
    where_exp: str,
    select_exp: str,
    param_columns: str,
) -> InventoryApiRecord:
    existing = get_inventory_api_by_idx(database_path, idx)
    if existing is None:
        raise ValueError("API를 찾을 수 없습니다.")

    name = validate_api_name(api_name)
    label = (display_name or "").strip()
    if not label:
        raise ValueError("디스플레이 명을 입력하세요.")
    if len(label) > _DISPLAY_NAME_MAX:
        raise ValueError(f"디스플레이 명은 {_DISPLAY_NAME_MAX}자를 넘을 수 없습니다.")
    desc = (description or "").strip()[:_DESCRIPTION_MAX]
    params = parse_param_columns(param_columns)
    if not params:
        raise ValueError("API 매개변수 컬럼을 1개 이상 선택하세요.")

    with get_connection(database_path) as connection:
        ensure_inventory_api_table(connection)
        if not table_exists(connection, existing.table_name):
            raise ValueError(f"데이터 테이블이 존재하지 않습니다: {existing.table_name}")
        allowed = set(list_table_columns(connection, existing.table_name))
        if not allowed:
            raise ValueError("테이블 컬럼 정보를 불러올 수 없습니다.")
        for col in params:
            if col not in allowed:
                raise ValueError(f"매개변수 컬럼이 테이블에 없습니다: {col}")
        validated_select = validate_select_exp(select_exp, allowed)
        validated_where = validate_where_exp(where_exp, allowed, params)
        fullpath = build_api_fullpath(name)
        if len(fullpath) > _API_FULLPATH_MAX:
            raise ValueError("API 경로가 너무 깁니다.")

        conflict = connection.execute(
            """
            SELECT idx FROM inventory_api
            WHERE (api_name = ? OR api_fullpath = ?) AND idx <> ?
            """,
            (name, fullpath, int(idx)),
        ).fetchone()
        if conflict is not None:
            raise ValueError(f"이미 사용 중인 API 이름입니다: {name}")

        connection.execute(
            """
            UPDATE inventory_api
            SET api_name = ?, display_name = ?, description = ?, api_fullpath = ?,
                where_exp = ?, select_exp = ?, param_columns = ?
            WHERE idx = ?
            """,
            (
                name,
                label,
                desc,
                fullpath,
                validated_where[:_WHERE_EXP_MAX],
                validated_select[:_SELECT_EXP_MAX],
                ",".join(params)[:_PARAM_COLUMNS_MAX],
                int(idx),
            ),
        )

    record = get_inventory_api_by_idx(database_path, idx)
    if record is None:
        raise ValueError("API 수정 후 조회에 실패했습니다.")
    return record


def delete_inventory_api(database_path: str | Path, idx: int) -> bool:
    with get_connection(database_path) as connection:
        ensure_inventory_api_table(connection)
        row = connection.execute(
            "SELECT idx FROM inventory_api WHERE idx = ?",
            (int(idx),),
        ).fetchone()
        if row is None:
            return False
        connection.execute("DELETE FROM inventory_api WHERE idx = ?", (int(idx),))
    return True


def delete_inventory_apis_by_table(database_path: str | Path, table_name: str) -> int:
    table = validate_inventory_table_name(table_name)
    with get_connection(database_path) as connection:
        ensure_inventory_api_table(connection)
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM inventory_api WHERE table_name = ?",
            (table,),
        ).fetchone()
        count = int(row["count"] or 0) if row else 0
        if count:
            connection.execute("DELETE FROM inventory_api WHERE table_name = ?", (table,))
    return count


def execute_inventory_api_query(
    database_path: str | Path,
    record: InventoryApiRecord,
    params: dict[str, str],
) -> list[dict[str, object]]:
    param_columns = parse_param_columns(record.param_columns)
    with get_connection(database_path) as connection:
        allowed = set(list_table_columns(connection, record.table_name))
        validate_select_exp(record.select_exp, allowed)
        validate_where_exp(record.where_exp, allowed, param_columns)
        where_sql, bind_order = compile_where_clause(record.where_exp, param_columns)
        values: list[str] = []
        for col in bind_order:
            if col not in params:
                raise ValueError(f"필수 매개변수가 없습니다: {col}")
            values.append(str(params[col]))

        quoted_table = quote_ident(record.table_name)
        sql = f"SELECT {record.select_exp} FROM {quoted_table} WHERE {where_sql}"
        rows = connection.execute(sql, tuple(values)).fetchall()
    return [dict(row) for row in rows]


def get_inventory_table_columns(database_path: str | Path, table_name: str) -> list[str]:
    table = validate_inventory_table_name(table_name)
    inventory = get_inventory_by_table_name(database_path, table)
    if inventory is None:
        raise ValueError("연결된 인벤토리를 찾을 수 없습니다.")
    with get_connection(database_path) as connection:
        if not table_exists(connection, table):
            raise ValueError(f"데이터 테이블이 존재하지 않습니다: {table}")
        return list_table_columns(connection, table)
