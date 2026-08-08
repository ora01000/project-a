"""Database engine: SQLite (default) or PostgreSQL via DATABASE_URL."""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Literal
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

Dialect = Literal["sqlite", "postgresql"]

_POSTGRES_SCHEMES = frozenset({"postgres", "postgresql"})


@dataclass(frozen=True)
class DatabaseConfig:
    dialect: Dialect
    sqlite_path: Path | None = None
    database_url: str | None = None


def parse_database_url(url: str | None) -> Dialect | None:
    text = (url or "").strip()
    if not text:
        return None
    parsed = urlparse(text)
    scheme = (parsed.scheme or "").lower()
    if scheme in _POSTGRES_SCHEMES:
        return "postgresql"
    if scheme in {"sqlite", "file"}:
        return "sqlite"
    raise ValueError(f"Unsupported DATABASE_URL scheme: {scheme or '(empty)'}")


def load_database_config(
    *,
    database_path: str | Path | None = None,
    database_url: str | None = None,
) -> DatabaseConfig:
    from backend.app.config import PROJECT_ROOT, AppSettings
    from backend.app.db.database import resolve_database_path

    env = AppSettings()
    url = (
        database_url
        if database_url is not None
        else (env.database_url or os.environ.get("DATABASE_URL", ""))
    ).strip()
    dialect = parse_database_url(url) if url else None
    if dialect == "postgresql":
        return DatabaseConfig(dialect="postgresql", database_url=url)
    path_raw = database_path if database_path is not None else env.database_path
    path = resolve_database_path(path_raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return DatabaseConfig(dialect="sqlite", sqlite_path=path, database_url=url or None)


def qmark_to_pyformat(sql: str) -> str:
    """Convert SQLite ``?`` placeholders to psycopg ``%s``.

    Literal ``%`` (e.g. ``LIKE 'sqlite_%'``) must be doubled for psycopg,
    otherwise it is treated as a placeholder marker.
    """
    escaped = sql.replace("%", "%%")
    return re.sub(r"\?", "%s", escaped)


class PostgresCursor:
    """sqlite3-like cursor wrapper (exposes ``lastrowid`` after INSERT)."""

    def __init__(self, cursor: Any, *, lastrowid: int | None = None) -> None:
        self._cursor = cursor
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def __getattr__(self, name: str):
        return getattr(self._cursor, name)


class PostgresConnection:
    """Thin adapter so callers can use ``.execute(sql, params)`` like sqlite3."""

    def __init__(self, raw: Any) -> None:
        self._raw = raw
        self.row_factory = None  # unused; rows are dict-like via cursor

    def execute(self, sql: str, parameters: tuple | list | None = None):
        converted = qmark_to_pyformat(sql)
        cursor = self._raw.cursor()
        cursor.execute(converted, parameters or ())
        lastrowid: int | None = None
        if re.match(r"^\s*INSERT\b", converted, flags=re.IGNORECASE):
            try:
                probe = self._raw.cursor()
                probe.execute("SELECT LASTVAL()")
                row = probe.fetchone()
                if row is not None:
                    value = row[0] if not hasattr(row, "keys") else next(iter(row.values()))
                    lastrowid = int(value)
            except Exception:
                lastrowid = None
        return PostgresCursor(cursor, lastrowid=lastrowid)

    def executemany(self, sql: str, seq_of_parameters) -> None:
        converted = qmark_to_pyformat(sql)
        cursor = self._raw.cursor()
        cursor.executemany(converted, seq_of_parameters)

    def executescript(self, script: str) -> None:
        # psycopg3 Connection.execute accepts multiple statements.
        self._raw.execute(script)

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        self._raw.close()

    def __enter__(self) -> PostgresConnection:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()
        self.close()


def connect_sqlite(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def connect_postgres(database_url: str) -> PostgresConnection:
    import psycopg
    from psycopg.rows import dict_row

    raw = psycopg.connect(database_url, row_factory=dict_row)
    return PostgresConnection(raw)


@contextmanager
def advisory_lock(connection: PostgresConnection, lock_key: int = 26080701) -> Iterator[None]:
    """Serialize schema init across pods (PostgreSQL only)."""
    connection.execute("SELECT pg_advisory_lock(?)", (lock_key,))
    try:
        yield
    finally:
        connection.execute("SELECT pg_advisory_unlock(?)", (lock_key,))


def ping_database(config: DatabaseConfig) -> bool:
    if config.dialect == "postgresql":
        assert config.database_url
        with connect_postgres(config.database_url) as conn:
            conn.execute("SELECT 1")
        return True
    assert config.sqlite_path
    with connect_sqlite(config.sqlite_path) as conn:
        conn.execute("SELECT 1")
    return True
