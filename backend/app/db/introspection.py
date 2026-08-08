"""Dialect-aware table/column introspection (SQLite + PostgreSQL)."""

from __future__ import annotations

import re
from typing import Any

_SAFE_IDENT = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")


def _quote_ident(name: str) -> str:
    if not _SAFE_IDENT.match(name):
        raise ValueError(f"Unsafe identifier: {name}")
    return '"' + name.replace('"', '""') + '"'


def is_postgres_connection(connection: Any) -> bool:
    from backend.app.db.engine import PostgresConnection

    return isinstance(connection, PostgresConnection)


def list_user_tables(connection: Any) -> set[str]:
    if is_postgres_connection(connection):
        rows = connection.execute(
            """
            SELECT tablename AS name
            FROM pg_tables
            WHERE schemaname = 'public'
            """
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    return {
        str(row["name"] if hasattr(row, "keys") else row[0])
        for row in rows
    }


def list_table_columns(connection: Any, table_name: str) -> set[str]:
    if is_postgres_connection(connection):
        rows = connection.execute(
            """
            SELECT a.attname AS name
            FROM pg_attribute a
            JOIN pg_class r ON a.attrelid = r.oid
            JOIN pg_namespace n ON r.relnamespace = n.oid
            WHERE n.nspname = 'public'
              AND r.relname = ?
              AND a.attnum > 0
              AND NOT a.attisdropped
            """,
            (table_name,),
        ).fetchall()
    else:
        rows = connection.execute(
            f"PRAGMA table_info({_quote_ident(table_name)})"
        ).fetchall()
    return {
        str(row["name"] if hasattr(row, "keys") else row[0])
        for row in rows
    }


def ci_order_clause(connection: Any, *columns: str) -> str:
    """Case-insensitive ORDER BY fragment (SQLite NOCASE / Postgres LOWER)."""
    if not columns:
        return ""
    if is_postgres_connection(connection):
        return ", ".join(f"LOWER({column}) ASC" for column in columns)
    return ", ".join(f"{column} COLLATE NOCASE ASC" for column in columns)


def pk_autoincrement_sql(connection: Any, column: str = "idx") -> str:
    """Primary-key column DDL for dynamic inventory tables."""
    ident = _quote_ident(column)
    if is_postgres_connection(connection):
        return f"{ident} BIGSERIAL PRIMARY KEY"
    return f"{ident} INTEGER PRIMARY KEY AUTOINCREMENT"


def ensure_table_idx_serial(connection: Any, table_name: str) -> None:
    """Attach a sequence default to ``idx`` when missing (PostgreSQL only).

    Migrated inventory tables were created as ``BIGINT PRIMARY KEY`` without
    SERIAL, so INSERT without ``idx`` fails with NOT NULL.
    """
    if not is_postgres_connection(connection):
        return
    if not _SAFE_IDENT.match(table_name):
        raise ValueError(f"Unsafe table name: {table_name}")
    if table_name not in list_user_tables(connection):
        return

    quoted_table = _quote_ident(table_name)
    default_row = connection.execute(
        """
        SELECT column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = ?
          AND column_name = 'idx'
        """,
        (table_name,),
    ).fetchone()
    if default_row is None:
        return
    current_default = (
        default_row["column_default"] if hasattr(default_row, "keys") else default_row[0]
    )
    if current_default:
        return

    seq_name = f"{table_name}_idx_seq"
    quoted_seq = _quote_ident(seq_name)
    # nextval()/setval() need a quoted regclass literal for hyphenated names.
    seq_reg = '"' + seq_name.replace('"', '""') + '"'
    connection.execute(f"CREATE SEQUENCE IF NOT EXISTS {quoted_seq}")
    connection.execute(
        f"ALTER TABLE {quoted_table} "
        f"ALTER COLUMN idx SET DEFAULT nextval('{seq_reg}')"
    )
    connection.execute(f"ALTER SEQUENCE {quoted_seq} OWNED BY {quoted_table}.idx")
    connection.execute(
        f"""
        SELECT setval(
            '{seq_reg}',
            COALESCE((SELECT MAX(idx) FROM {quoted_table}), 1),
            true
        )
        """
    )
