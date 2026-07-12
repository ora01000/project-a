import logging
import sqlite3
from pathlib import Path

from backend.app.agents.registry import AGENT_DEFINITIONS
from backend.app.config import PROJECT_ROOT
from backend.app.db.seed import INITIAL_USERS

logger = logging.getLogger(__name__)


def _encode_mcp_server_keys(keys: list[str]) -> str:
    return ",".join(keys)

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


def _apply_migrations(connection: sqlite3.Connection) -> None:
    job_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
    }
    if "job_plan" not in job_columns:
        connection.execute("ALTER TABLE jobs ADD COLUMN job_plan TEXT")
    if "execution_result" not in job_columns:
        connection.execute("ALTER TABLE jobs ADD COLUMN execution_result TEXT")
    if "notify_channel" not in job_columns:
        connection.execute(
            "ALTER TABLE jobs ADD COLUMN notify_channel VARCHAR(30) NOT NULL DEFAULT 'integrated_chat'"
        )

    tables = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "signup_notifications" not in tables:
        connection.execute(
            """
            CREATE TABLE signup_notifications (
                idx INTEGER PRIMARY KEY AUTOINCREMENT,
                user_idx INTEGER NOT NULL,
                target_user VARCHAR(50) NOT NULL,
                title VARCHAR(200) NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_idx) REFERENCES users(idx)
            )
            """
        )


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


def seed_initial_agents(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT COUNT(*) AS count FROM agents").fetchone()
    existing_count = int(row["count"]) if row else 0
    if existing_count > 0:
        logger.info("Skip agent seeding: agents table already has %s record(s)", existing_count)
        return 0

    seed_rows = [
        {
            "agent_id": definition.agent_id,
            "name": definition.name,
            "role": definition.role,
            "system_prompt": definition.system_prompt,
            "mcp_server_keys": _encode_mcp_server_keys(definition.mcp_server_keys),
        }
        for definition in AGENT_DEFINITIONS
    ]
    connection.executemany(
        """
        INSERT INTO agents (agent_id, name, role, system_prompt, mcp_server_keys)
        VALUES (:agent_id, :name, :role, :system_prompt, :mcp_server_keys)
        """,
        seed_rows,
    )
    connection.commit()
    logger.info("Seeded %s initial agent record(s)", len(seed_rows))
    return len(seed_rows)


def sync_missing_agents(connection: sqlite3.Connection) -> int:
    existing_ids = {
        str(row["agent_id"])
        for row in connection.execute("SELECT agent_id FROM agents").fetchall()
    }
    missing_definitions = [
        definition for definition in AGENT_DEFINITIONS if definition.agent_id not in existing_ids
    ]
    if not missing_definitions:
        return 0

    seed_rows = [
        {
            "agent_id": definition.agent_id,
            "name": definition.name,
            "role": definition.role,
            "system_prompt": definition.system_prompt,
            "mcp_server_keys": _encode_mcp_server_keys(definition.mcp_server_keys),
        }
        for definition in missing_definitions
    ]
    connection.executemany(
        """
        INSERT INTO agents (agent_id, name, role, system_prompt, mcp_server_keys)
        VALUES (:agent_id, :name, :role, :system_prompt, :mcp_server_keys)
        """,
        seed_rows,
    )
    connection.commit()
    logger.info("Synced %s missing agent record(s)", len(seed_rows))
    return len(seed_rows)


def init_database(database_path: str | Path | None = None) -> Path:
    path = resolve_database_path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with get_connection(path) as connection:
        _apply_schema(connection)
        _apply_migrations(connection)
        connection.commit()
        seed_initial_users(connection)
        seed_initial_agents(connection)
        sync_missing_agents(connection)

    logger.info("SQLite database initialized at %s", path)
    return path
