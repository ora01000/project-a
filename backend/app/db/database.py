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
    user_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(users)").fetchall()
    }
    if "agents" not in user_columns:
        connection.execute(
            "ALTER TABLE users ADD COLUMN agents VARCHAR(200) NOT NULL DEFAULT ''"
        )
    if "last_login" not in user_columns:
        connection.execute("ALTER TABLE users ADD COLUMN last_login TEXT")
    if "band" not in user_columns:
        connection.execute("ALTER TABLE users ADD COLUMN band INTEGER NOT NULL DEFAULT 1")
        connection.execute("UPDATE users SET band = 1 WHERE band IS NULL OR band = 0")

    job_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
    }
    if "job_plan" not in job_columns:
        connection.execute("ALTER TABLE jobs ADD COLUMN job_plan TEXT")
    if "original_job_plan" not in job_columns:
        connection.execute("ALTER TABLE jobs ADD COLUMN original_job_plan TEXT")
        # Backfill existing plans as the original baseline for restore.
        connection.execute(
            """
            UPDATE jobs
            SET original_job_plan = job_plan
            WHERE original_job_plan IS NULL AND job_plan IS NOT NULL
            """
        )
    if "execution_result" not in job_columns:
        connection.execute("ALTER TABLE jobs ADD COLUMN execution_result TEXT")
    if "notify_channel" not in job_columns:
        connection.execute(
            "ALTER TABLE jobs ADD COLUMN notify_channel VARCHAR(30) NOT NULL DEFAULT 'integrated_chat'"
        )
    if "actual_completion_time" not in job_columns:
        connection.execute("ALTER TABLE jobs ADD COLUMN actual_completion_time TEXT")
    if "sr_num" not in job_columns:
        # Format length is 16 (e.g. SR20260717_00001); use 20 for headroom.
        connection.execute("ALTER TABLE jobs ADD COLUMN sr_num VARCHAR(20)")

    # Prefer userid in jobs.requester / jobs.approver (legacy rows used username).
    connection.execute(
        "UPDATE jobs SET requester = 'isyun' WHERE requester = '윤인수'"
    )
    connection.execute(
        "UPDATE jobs SET requester = 'loadan' WHERE requester = '안세훈'"
    )
    connection.execute(
        "UPDATE jobs SET approver = 'isyun' WHERE approver = '윤인수'"
    )
    connection.execute(
        "UPDATE jobs SET approver = 'loadan' WHERE approver = '안세훈'"
    )

    # Backfill date-only request/completion fields with 00:00:00.
    connection.execute(
        """
        UPDATE jobs
        SET request_date = request_date || ' 00:00:00'
        WHERE request_date IS NOT NULL
          AND length(trim(request_date)) = 10
          AND request_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
        """
    )
    connection.execute(
        """
        UPDATE jobs
        SET completion_request_date = completion_request_date || ' 00:00:00'
        WHERE completion_request_date IS NOT NULL
          AND length(trim(completion_request_date)) = 10
          AND completion_request_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
        """
    )

    # Backfill SR numbers from request_date + idx (e.g. SR20260717_00001).
    from backend.app.db.job_datetime import build_sr_num

    for row in connection.execute(
        """
        SELECT idx, request_date
        FROM jobs
        WHERE sr_num IS NULL OR trim(sr_num) = ''
        """
    ).fetchall():
        try:
            sr_num = build_sr_num(str(row["request_date"]), int(row["idx"]))
        except ValueError:
            logger.warning(
                "Skipped sr_num backfill for jobs.idx=%s request_date=%r",
                row["idx"],
                row["request_date"],
            )
            continue
        connection.execute(
            "UPDATE jobs SET sr_num = ? WHERE idx = ?",
            (sr_num, int(row["idx"])),
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
    if "notice_board" not in tables:
        connection.execute(
            """
            CREATE TABLE notice_board (
                idx INTEGER PRIMARY KEY AUTOINCREMENT,
                writer VARCHAR(50) NOT NULL,
                write_date TEXT NOT NULL,
                from_date TEXT NOT NULL,
                until_date TEXT NOT NULL,
                title VARCHAR(100) NOT NULL,
                notice TEXT NOT NULL,
                welcome_popup INTEGER NOT NULL DEFAULT 0
            )
            """
        )
    if "inventory" not in tables:
        connection.execute(
            """
            CREATE TABLE inventory (
                idx INTEGER PRIMARY KEY AUTOINCREMENT,
                inventory_name VARCHAR(100) NOT NULL,
                inventory_file VARCHAR(300) NOT NULL,
                file_ext VARCHAR(15) NOT NULL,
                chunk_type INTEGER NOT NULL,
                chunk_size INTEGER NOT NULL DEFAULT 0,
                chunk_overlap INTEGER NOT NULL DEFAULT 50,
                n_results INTEGER NOT NULL DEFAULT 100,
                db_type VARCHAR(10),
                modified INTEGER NOT NULL DEFAULT 0
            )
            """
        )
    else:
        inventory_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(inventory)").fetchall()
        }
        if "chunk_size" not in inventory_columns:
            connection.execute(
                "ALTER TABLE inventory ADD COLUMN chunk_size INTEGER NOT NULL DEFAULT 0"
            )
        if "chunk_overlap" not in inventory_columns:
            connection.execute(
                "ALTER TABLE inventory ADD COLUMN chunk_overlap INTEGER NOT NULL DEFAULT 50"
            )
        if "n_results" not in inventory_columns:
            connection.execute(
                "ALTER TABLE inventory ADD COLUMN n_results INTEGER NOT NULL DEFAULT 100"
            )
        if "db_type" not in inventory_columns:
            connection.execute("ALTER TABLE inventory ADD COLUMN db_type VARCHAR(10)")

    _ensure_k8s_inventory_tables(connection)


def _ensure_k8s_inventory_tables(connection: sqlite3.Connection) -> None:
    tables = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }

    if "k8s_cluster" not in tables:
        connection.execute(
            """
            CREATE TABLE k8s_cluster (
                idx INTEGER PRIMARY KEY AUTOINCREMENT,
                cluster_name VARCHAR(50) NOT NULL UNIQUE,
                last_update TEXT
            )
            """
        )

    needs_rebuild = False
    if "k8s_nodes" not in tables:
        needs_rebuild = True
    else:
        node_columns = {
            row["name"]: str(row["type"]).upper()
            for row in connection.execute("PRAGMA table_info(k8s_nodes)").fetchall()
        }
        cluster_type = node_columns.get("cluster_id", "")
        # Legacy schema stored cluster name as VARCHAR(50).
        if "VARCHAR" in cluster_type or "CHAR" in cluster_type or "TEXT" in cluster_type:
            needs_rebuild = True
            logger.info("Migrating k8s_* tables: cluster_id VARCHAR -> INTEGER (k8s_cluster.idx)")

    if needs_rebuild:
        for table_name in (
            "k8s_pods",
            "k8s_pvcs",
            "k8s_deployments",
            "k8s_namespaces",
            "k8s_nodes",
        ):
            connection.execute(f"DROP TABLE IF EXISTS {table_name}")

        connection.execute(
            """
            CREATE TABLE k8s_nodes (
                idx INTEGER PRIMARY KEY AUTOINCREMENT,
                cluster_id INTEGER NOT NULL,
                node_name VARCHAR(50) NOT NULL,
                node_cpu INTEGER,
                node_mem INTEGER,
                node_os VARCHAR(50),
                node_k8s_ver VARCHAR(50),
                FOREIGN KEY (cluster_id) REFERENCES k8s_cluster(idx)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE k8s_namespaces (
                idx INTEGER PRIMARY KEY AUTOINCREMENT,
                cluster_id INTEGER NOT NULL,
                namespace VARCHAR(50) NOT NULL,
                okd_display_name VARCHAR(100),
                resource_quota_cpu_limit REAL,
                resource_quota_mem_limit INTEGER,
                resource_quota_pod_limit INTEGER,
                okd_egressip1 VARCHAR(20),
                okd_egressip2 VARCHAR(20),
                FOREIGN KEY (cluster_id) REFERENCES k8s_cluster(idx)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE k8s_deployments (
                idx INTEGER PRIMARY KEY AUTOINCREMENT,
                cluster_id INTEGER NOT NULL,
                namespace_id INTEGER NOT NULL,
                name VARCHAR(50) NOT NULL,
                type VARCHAR(20) NOT NULL,
                replicas INTEGER,
                resource_cpu_request REAL,
                resource_mem_request INTEGER,
                resource_cpu_limit REAL,
                resource_mem_limit INTEGER,
                containers_cnt INTEGER,
                containers_name VARCHAR(300),
                containers_image VARCHAR(500),
                FOREIGN KEY (cluster_id) REFERENCES k8s_cluster(idx),
                FOREIGN KEY (namespace_id) REFERENCES k8s_namespaces(idx)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE k8s_pvcs (
                idx INTEGER PRIMARY KEY AUTOINCREMENT,
                cluster_id INTEGER NOT NULL,
                namespace_id INTEGER NOT NULL,
                deployment_id INTEGER,
                name VARCHAR(50) NOT NULL,
                storage_class VARCHAR(20),
                capacity INTEGER,
                used INTEGER,
                access_mode VARCHAR(20),
                FOREIGN KEY (cluster_id) REFERENCES k8s_cluster(idx),
                FOREIGN KEY (namespace_id) REFERENCES k8s_namespaces(idx),
                FOREIGN KEY (deployment_id) REFERENCES k8s_deployments(idx)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE k8s_pods (
                idx INTEGER PRIMARY KEY AUTOINCREMENT,
                cluster_id INTEGER NOT NULL,
                namespace_id INTEGER NOT NULL,
                deployment_id INTEGER,
                name VARCHAR(50) NOT NULL,
                scheduled_node INTEGER,
                FOREIGN KEY (cluster_id) REFERENCES k8s_cluster(idx),
                FOREIGN KEY (namespace_id) REFERENCES k8s_namespaces(idx),
                FOREIGN KEY (deployment_id) REFERENCES k8s_deployments(idx),
                FOREIGN KEY (scheduled_node) REFERENCES k8s_nodes(idx)
            )
            """
        )

    _sync_k8s_cluster_rows(connection)


def _sync_k8s_cluster_rows(connection: sqlite3.Connection) -> None:
    from backend.app.agents.k8s_agent import K8S_CLUSTER_SPECS

    for cluster_name, _display_name in K8S_CLUSTER_SPECS:
        connection.execute(
            """
            INSERT INTO k8s_cluster (cluster_name, last_update)
            VALUES (?, NULL)
            ON CONFLICT(cluster_name) DO NOTHING
            """,
            (cluster_name,),
        )


def seed_initial_users(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()
    existing_count = int(row["count"]) if row else 0
    if existing_count > 0:
        logger.info("Skip user seeding: users table already has %s record(s)", existing_count)
        return 0

    connection.executemany(
        """
        INSERT INTO users (userid, email, username, password, depart, role, band)
        VALUES (:userid, :email, :username, :password, :depart, :role, :band)
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
