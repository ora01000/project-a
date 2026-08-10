import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.db.database import get_connection
from backend.app.db.engine import is_integrity_error
from backend.app.db.roles import is_admin_role
from backend.app.middleware.session_auth import get_request_auth_user

router = APIRouter(tags=["debug"])

# Per-cluster k8s inventory tables use hyphens (e.g. dprv6-k8s_k8s_nodes).
# Quoted identifiers make hyphenated names safe as long as quotes/control chars are rejected.
_SAFE_IDENT = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")


class TableSnapshot(BaseModel):
    name: str
    columns: list[str]
    column_types: dict[str, str] = Field(default_factory=dict)
    rows: list[dict[str, Any]]
    row_count: int
    primary_key: str | None = None


class TablesDebugResponse(BaseModel):
    tables: list[TableSnapshot]


class DeleteTableRowsRequest(BaseModel):
    idx_list: list[int] = Field(min_length=1)


class DeleteTableRowsResponse(BaseModel):
    deleted: int


class DropTableRequest(BaseModel):
    confirm_name: str = Field(min_length=1)


class DropTableResponse(BaseModel):
    dropped: str


class UpdateTableRowRequest(BaseModel):
    idx: int
    values: dict[str, Any]


class UpdateTableRowResponse(BaseModel):
    updated: int


def _require_admin(request: Request) -> None:
    viewer = get_request_auth_user(request)
    if not is_admin_role(viewer.role):
        raise HTTPException(status_code=403, detail="관리자만 수행할 수 있습니다.")


def _quote_ident(name: str) -> str:
    if not _SAFE_IDENT.match(name):
        raise ValueError(f"Unsafe table name: {name}")
    return f'"{name}"'


def _list_user_tables(connection: Any) -> list[str]:
    rows = connection.execute(
        """
        SELECT tablename AS name
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY tablename
        """
    ).fetchall()
    return [str(row["name"]) for row in rows]


def _table_column_meta(
    connection: Any,
    table_name: str,
) -> tuple[list[str], dict[str, str], dict[str, bool], str | None]:
    columns: list[str] = []
    column_types: dict[str, str] = {}
    notnull: dict[str, bool] = {}
    primary_key: str | None = None

    # Resolve against public schema; inventory tables may contain hyphens.
    column_info = connection.execute(
        """
        SELECT
            a.attname AS name,
            pg_catalog.format_type(a.atttypid, a.atttypmod) AS type,
            CASE WHEN a.attnotnull THEN 1 ELSE 0 END AS notnull,
            CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM pg_constraint c
                    WHERE c.conrelid = a.attrelid
                      AND c.contype = 'p'
                      AND a.attnum = ANY (c.conkey)
                ) THEN 1
                ELSE 0
            END AS pk
        FROM pg_attribute a
        JOIN pg_class r ON a.attrelid = r.oid
        JOIN pg_namespace n ON r.relnamespace = n.oid
        WHERE n.nspname = 'public'
          AND r.relname = ?
          AND a.attnum > 0
          AND NOT a.attisdropped
        ORDER BY a.attnum
        """,
        (table_name,),
    ).fetchall()

    for col in column_info:
        name = str(col["name"])
        columns.append(name)
        column_types[name] = str(col["type"] or "")
        notnull[name] = bool(int(col["notnull"]))
        if int(col["pk"]) == 1:
            primary_key = name
    return columns, column_types, notnull, primary_key


def _primary_key_column(connection: Any, table_name: str) -> str | None:
    _columns, _types, _notnull, primary_key = _table_column_meta(connection, table_name)
    return primary_key


def _coerce_value(raw: Any, sqlite_type: str) -> Any:
    if raw is None:
        return None
    if isinstance(raw, str) and raw.strip().lower() == "null":
        return None
    type_upper = (sqlite_type or "").upper()
    if "INT" in type_upper:
        if isinstance(raw, bool):
            return int(raw)
        if isinstance(raw, (int, float)):
            return int(raw)
        text = str(raw).strip()
        if text == "":
            return None
        return int(text)
    if any(token in type_upper for token in ("REAL", "FLOA", "DOUB")):
        if isinstance(raw, (int, float)):
            return float(raw)
        text = str(raw).strip()
        if text == "":
            return None
        return float(text)
    if isinstance(raw, (dict, list)):
        return json.dumps(raw, ensure_ascii=False)
    return str(raw) if raw is not None else None


@router.get("/debug/tables", response_model=TablesDebugResponse)
async def get_all_tables(request: Request) -> TablesDebugResponse:
    database_path = request.app.state.database_path
    snapshots: list[TableSnapshot] = []

    with get_connection(database_path) as connection:
        for table_name in _list_user_tables(connection):
            columns, column_types, _notnull, primary_key = _table_column_meta(connection, table_name)
            quoted = _quote_ident(table_name)
            data_rows = connection.execute(f"SELECT * FROM {quoted}").fetchall()
            rows = [{key: row[key] for key in row.keys()} for row in data_rows]
            snapshots.append(
                TableSnapshot(
                    name=table_name,
                    columns=columns,
                    column_types=column_types,
                    rows=rows,
                    row_count=len(rows),
                    primary_key=primary_key,
                )
            )

    return TablesDebugResponse(tables=snapshots)


@router.post("/debug/tables/{table_name}/delete", response_model=DeleteTableRowsResponse)
async def delete_table_rows(
    table_name: str,
    payload: DeleteTableRowsRequest,
    request: Request,
) -> DeleteTableRowsResponse:
    try:
        quoted_table = _quote_ident(table_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    database_path = request.app.state.database_path
    with get_connection(database_path) as connection:
        if table_name not in _list_user_tables(connection):
            raise HTTPException(status_code=404, detail=f"테이블을 찾을 수 없습니다: {table_name}")

        primary_key = _primary_key_column(connection, table_name)
        if primary_key is None:
            raise HTTPException(status_code=400, detail="삭제할 기본 키가 없습니다.")
        if primary_key != "idx":
            raise HTTPException(status_code=400, detail="idx 기본 키 테이블만 삭제할 수 있습니다.")

        try:
            quoted_pk = _quote_ident(primary_key)
            placeholders = ", ".join("?" for _ in payload.idx_list)
            cursor = connection.execute(
                f"DELETE FROM {quoted_table} WHERE {quoted_pk} IN ({placeholders})",
                tuple(payload.idx_list),
            )
            connection.commit()
        except Exception as exc:
            if "integrity" not in type(exc).__name__.lower() and "foreign key" not in str(exc).lower():
                raise
            raise HTTPException(
                status_code=400,
                detail=f"참조 무결성 때문에 삭제할 수 없습니다: {exc}",
            ) from exc

    return DeleteTableRowsResponse(deleted=int(cursor.rowcount))


@router.post("/debug/tables/{table_name}/drop", response_model=DropTableResponse)
async def drop_table(
    table_name: str,
    payload: DropTableRequest,
    request: Request,
) -> DropTableResponse:
    """DROP TABLE — requires typing the exact table name in confirm_name."""
    _require_admin(request)
    confirm = (payload.confirm_name or "").strip()
    if confirm != table_name:
        raise HTTPException(
            status_code=400,
            detail="확인용 테이블 이름이 일치하지 않습니다.",
        )
    try:
        quoted_table = _quote_ident(table_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    database_path = request.app.state.database_path
    with get_connection(database_path) as connection:
        if table_name not in _list_user_tables(connection):
            raise HTTPException(status_code=404, detail=f"테이블을 찾을 수 없습니다: {table_name}")
        try:
            connection.execute(f"DROP TABLE IF EXISTS {quoted_table} CASCADE")
            connection.commit()
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"테이블 삭제에 실패했습니다: {exc}",
            ) from exc

    return DropTableResponse(dropped=table_name)


@router.post("/debug/tables/{table_name}/update", response_model=UpdateTableRowResponse)
async def update_table_row(
    table_name: str,
    payload: UpdateTableRowRequest,
    request: Request,
) -> UpdateTableRowResponse:
    try:
        quoted_table = _quote_ident(table_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    database_path = request.app.state.database_path
    with get_connection(database_path) as connection:
        if table_name not in _list_user_tables(connection):
            raise HTTPException(status_code=404, detail=f"테이블을 찾을 수 없습니다: {table_name}")

        columns, column_types, notnull, primary_key = _table_column_meta(connection, table_name)
        if primary_key is None:
            raise HTTPException(status_code=400, detail="수정할 기본 키가 없습니다.")
        if primary_key != "idx":
            raise HTTPException(status_code=400, detail="idx 기본 키 테이블만 수정할 수 있습니다.")

        allowed = set(columns) - {primary_key}
        unknown = [key for key in payload.values if key not in allowed and key != primary_key]
        if unknown:
            raise HTTPException(status_code=400, detail=f"알 수 없는 컬럼: {', '.join(unknown)}")

        updates = {key: value for key, value in payload.values.items() if key in allowed}
        if not updates:
            raise HTTPException(status_code=400, detail="수정할 컬럼이 없습니다.")

        coerced: dict[str, Any] = {}
        for key, value in updates.items():
            try:
                coerced_value = _coerce_value(value, column_types.get(key, ""))
            except (TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"컬럼 '{key}' 값 형식이 올바르지 않습니다: {exc}",
                ) from exc
            if coerced_value is None and notnull.get(key, False):
                raise HTTPException(status_code=400, detail=f"컬럼 '{key}'은(는) NULL을 허용하지 않습니다.")
            coerced[key] = coerced_value

        quoted_pk = _quote_ident(primary_key)
        set_clause = ", ".join(f"{_quote_ident(key)} = ?" for key in coerced)
        params = (*coerced.values(), payload.idx)
        try:
            cursor = connection.execute(
                f"UPDATE {quoted_table} SET {set_clause} WHERE {quoted_pk} = ?",
                params,
            )
            connection.commit()
        except Exception as exc:
            if is_integrity_error(exc) or "integrity" in type(exc).__name__.lower():
                raise HTTPException(
                    status_code=400,
                    detail=f"무결성 제약으로 수정할 수 없습니다: {exc}",
                ) from exc
            if "psycopg" in type(exc).__module__ or type(exc).__name__.lower().startswith("error"):
                raise HTTPException(status_code=400, detail=f"수정에 실패했습니다: {exc}") from exc
            raise

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"레코드를 찾을 수 없습니다: idx={payload.idx}")

    return UpdateTableRowResponse(updated=int(cursor.rowcount))
