"""PostgreSQL database bootstrap (DATABASE_URL required)."""

from __future__ import annotations

import logging
from pathlib import Path

from backend.app.config import PROJECT_ROOT
from backend.app.db.seed import INITIAL_USERS

logger = logging.getLogger(__name__)

SCHEMA_POSTGRES_PATH = Path(__file__).with_name("schema.postgres.sql")
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "app.db"
POSTGRES_STATE_TOKEN = Path("/var/run/project-a/postgresql")


def resolve_database_path(database_path: str | Path | None = None) -> Path:
    """Resolve a path token used by app state (legacy name; not an SQLite file)."""
    if database_path is None:
        return DEFAULT_DATABASE_PATH

    path = Path(database_path)
    if not path.is_absolute():
        return PROJECT_ROOT / path
    return path


def get_connection(database_path: str | Path | None = None):
    """Return a PostgresConnection. ``database_path`` is ignored when DATABASE_URL is set."""
    del database_path  # kept for call-site compatibility
    from backend.app.db.engine import connect_postgres, load_database_config

    config = load_database_config()
    return connect_postgres(config.database_url)


def seed_initial_users(connection) -> int:
    row = connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()
    existing_count = int(row["count"]) if row else 0
    if existing_count > 0:
        logger.info("Skip user seeding: users table already has %s record(s)", existing_count)
        return 0

    rows = [
        (
            user["userid"],
            user["email"],
            user["username"],
            user["password"],
            user["depart"],
            user["role"],
            user["band"],
        )
        for user in INITIAL_USERS
    ]
    connection.executemany(
        """
        INSERT INTO users (userid, email, username, password, depart, role, band)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    connection.commit()
    logger.info("Seeded %s initial user record(s)", len(INITIAL_USERS))
    return len(INITIAL_USERS)


def init_database(database_path: str | Path | None = None) -> Path:
    del database_path  # call sites pass yaml path; Postgres uses DATABASE_URL only
    from backend.app.db.engine import (
        advisory_lock,
        connect_postgres,
        load_database_config,
    )

    config = load_database_config()
    schema_sql = SCHEMA_POSTGRES_PATH.read_text(encoding="utf-8")
    with connect_postgres(config.database_url) as connection:
        with advisory_lock(connection):
            connection.executescript(schema_sql)
            # Legacy chat-notification table; signup now uses jobs (job_type=10).
            connection.execute("DROP TABLE IF EXISTS signup_notifications")
            seed_initial_users(connection)
    logger.info("PostgreSQL database initialized via DATABASE_URL")
    return POSTGRES_STATE_TOKEN
