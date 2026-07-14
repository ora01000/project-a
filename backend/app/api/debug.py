import re
import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.db.database import get_connection

router = APIRouter(tags=["debug"])

_SAFE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class TableSnapshot(BaseModel):
    name: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    primary_key: str | None = None


class TablesDebugResponse(BaseModel):
    tables: list[TableSnapshot]


class DeleteTableRowsRequest(BaseModel):
    idx_list: list[int] = Field(min_length=1)


class DeleteTableRowsResponse(BaseModel):
    deleted: int


def _quote_ident(name: str) -> str:
    if not _SAFE_IDENT.match(name):
        raise ValueError(f"Unsafe table name: {name}")
    return f'"{name}"'


def _list_user_tables(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    return [str(row["name"]) for row in rows]


def _primary_key_column(connection: sqlite3.Connection, table_name: str) -> str | None:
    quoted = _quote_ident(table_name)
    column_info = connection.execute(f"PRAGMA table_info({quoted})").fetchall()
    for col in column_info:
        if int(col["pk"]) == 1:
            return str(col["name"])
    return None


@router.get("/debug/tables", response_model=TablesDebugResponse)
async def get_all_tables(request: Request) -> TablesDebugResponse:
    database_path = request.app.state.database_path
    snapshots: list[TableSnapshot] = []

    with get_connection(database_path) as connection:
        for table_name in _list_user_tables(connection):
            quoted = _quote_ident(table_name)
            column_info = connection.execute(f"PRAGMA table_info({quoted})").fetchall()
            columns = [str(col["name"]) for col in column_info]
            primary_key = next(
                (str(col["name"]) for col in column_info if int(col["pk"]) == 1),
                None,
            )
            data_rows = connection.execute(f"SELECT * FROM {quoted}").fetchall()
            rows = [{key: row[key] for key in row.keys()} for row in data_rows]
            snapshots.append(
                TableSnapshot(
                    name=table_name,
                    columns=columns,
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
        except sqlite3.IntegrityError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"참조 무결성 때문에 삭제할 수 없습니다: {exc}",
            ) from exc

    return DeleteTableRowsResponse(deleted=int(cursor.rowcount))
