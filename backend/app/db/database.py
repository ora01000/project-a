import logging
import sqlite3
from pathlib import Path

from backend.app.config import PROJECT_ROOT
from backend.app.db.seed import INITIAL_USERS

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "app.db"


def resolve_database_path(database_path: str | Path | None = None) -> Path:
    if database_path is None:
        return DEFAULT_DATABASE_PATH

    path = Path(database_path)
    if not path.is_absolute():
        return PROJECT_ROOT / path
    return path


def get_connection(database_path: str | Path | None = None) -> sqlite3.Connection:
    path = resolve_database_path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _apply_schema(connection: sqlite3.Connection) -> None:
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    connection.executescript(schema_sql)


def seed_initial_users(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()
    existing_count = int(row["count"]) if row else 0
    if existing_count > 0:
        logger.info("Skip user seeding: users table already has %s record(s)", existing_count)
        return 0

    connection.executemany(
        """
        INSERT INTO users (userid, email, username, password, depart, role)
        VALUES (:userid, :email, :username, :password, :depart, :role)
        """,
        INITIAL_USERS,
    )
    connection.commit()
    logger.info("Seeded %s initial user record(s)", len(INITIAL_USERS))
    return len(INITIAL_USERS)


def init_database(database_path: str | Path | None = None) -> Path:
    path = resolve_database_path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with get_connection(path) as connection:
        _apply_schema(connection)
        connection.commit()
        seed_initial_users(connection)

    logger.info("SQLite database initialized at %s", path)
    return path
