"""Database engine: PostgreSQL via DATABASE_URL (required)."""

from __future__ import annotations

import logging
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Literal
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

Dialect = Literal["postgresql"]

_POSTGRES_SCHEMES = frozenset({"postgres", "postgresql"})


@dataclass(frozen=True)
class DatabaseConfig:
    dialect: Dialect
    database_url: str


def parse_database_url(url: str | None) -> Dialect:
    text = (url or "").strip()
    if not text:
        raise ValueError("DATABASE_URL is required (postgresql://...)")
    parsed = urlparse(text)
    scheme = (parsed.scheme or "").lower()
    if scheme in _POSTGRES_SCHEMES:
        return "postgresql"
    raise ValueError(
        f"Unsupported DATABASE_URL scheme: {scheme or '(empty)'} "
        "(PostgreSQL only; use postgresql://...)"
    )


def load_database_config(*, database_url: str | None = None) -> DatabaseConfig:
    from backend.app.config import AppSettings

    env = AppSettings()
    url = (
        database_url
        if database_url is not None
        else (env.database_url or os.environ.get("DATABASE_URL", ""))
    ).strip()
    parse_database_url(url)
    return DatabaseConfig(dialect="postgresql", database_url=url)


def qmark_to_pyformat(sql: str) -> str:
    """Convert ``?`` placeholders to psycopg ``%s``.

    Literal ``%`` (e.g. ``LIKE 'sqlite_%'``) must be doubled for psycopg,
    otherwise it is treated as a placeholder marker.
    """
    escaped = sql.replace("%", "%%")
    return re.sub(r"\?", "%s", escaped)


class PostgresCursor:
    """Cursor wrapper exposing ``lastrowid`` after INSERT."""

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
    """Thin adapter so callers can use ``.execute(sql, params)`` with ``?`` placeholders."""

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


def connect_postgres(database_url: str) -> PostgresConnection:
    import psycopg
    from psycopg.rows import dict_row

    raw = psycopg.connect(database_url, row_factory=dict_row)
    return PostgresConnection(raw)


def is_integrity_error(exc: BaseException) -> bool:
    from psycopg.errors import IntegrityError

    return isinstance(exc, IntegrityError)


@contextmanager
def advisory_lock(connection: PostgresConnection, lock_key: int = 26080701) -> Iterator[None]:
    """Serialize schema init across pods."""
    connection.execute("SELECT pg_advisory_lock(?)", (lock_key,))
    try:
        yield
    finally:
        connection.execute("SELECT pg_advisory_unlock(?)", (lock_key,))


def ping_database(config: DatabaseConfig) -> bool:
    with connect_postgres(config.database_url) as conn:
        conn.execute("SELECT 1")
    return True
