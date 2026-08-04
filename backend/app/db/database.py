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
    if "agentruntime" not in tables:
        connection.execute(
            """
            CREATE TABLE agentruntime (
                idx INTEGER PRIMARY KEY AUTOINCREMENT,
                type INTEGER NOT NULL,
                agent_name VARCHAR(50) NOT NULL,
                agent_id VARCHAR(50) NOT NULL,
                local_agent_id VARCHAR(50) NOT NULL DEFAULT '',
                description VARCHAR(255) NOT NULL,
                registered_date TEXT NOT NULL,
                service_id VARCHAR(20) NOT NULL,
                talkable INTEGER NOT NULL DEFAULT 1,
                is_orchestrator INTEGER NOT NULL DEFAULT 0,
                UNIQUE(type, agent_id)
            )
            """
        )

    _migrate_agentruntime_registered_datetime(connection)
    _migrate_agentruntime_local_agent_id(connection)
    _migrate_agentruntime_type_unique(connection)
    _migrate_agentruntime_drop_url_columns(connection)
    _migrate_agentruntime_talkable(connection)
    _migrate_agentruntime_is_orchestrator(connection)
    _drop_legacy_product_tables(connection)

    _ensure_jobs_table(connection)
    _migrate_jobs_approver_column(connection)
    _ensure_jobs_result_table(connection)
    _ensure_mynotes_table(connection)
    _ensure_k8s_inventory_tables(connection)


def _migrate_agentruntime_registered_datetime(connection: sqlite3.Connection) -> None:
    tables = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "agentruntime" not in tables:
        return

    from backend.app.db.agentruntime import normalize_registered_datetime

    rows = connection.execute("SELECT idx, registered_date FROM agentruntime").fetchall()
    updated = 0
    for row in rows:
        current = str(row["registered_date"])
        normalized = normalize_registered_datetime(current)
        if normalized != current:
            connection.execute(
                "UPDATE agentruntime SET registered_date = ? WHERE idx = ?",
                (normalized, int(row["idx"])),
            )
            updated += 1
    if updated:
        logger.info("Migrated %s agentruntime registered_date value(s) to datetime", updated)


def _migrate_agentruntime_local_agent_id(connection: sqlite3.Connection) -> None:
    tables = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "agentruntime" not in tables:
        return

    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(agentruntime)").fetchall()
    }
    if "local_agent_id" not in columns:
        connection.execute(
            "ALTER TABLE agentruntime ADD COLUMN local_agent_id VARCHAR(50) NOT NULL DEFAULT ''"
        )

    from backend.app.agents.registry import AGENT_DEFINITIONS
    from backend.app.db.agentruntime import build_axit_agent_id

    rows = connection.execute(
        "SELECT idx, agent_id, local_agent_id FROM agentruntime"
    ).fetchall()
    updated = 0
    for row in rows:
        current = str(row["local_agent_id"] or "").strip()
        if current:
            continue
        axit_agent_id = str(row["agent_id"])
        for definition in AGENT_DEFINITIONS:
            if build_axit_agent_id(definition.agent_id) == axit_agent_id:
                connection.execute(
                    "UPDATE agentruntime SET local_agent_id = ? WHERE idx = ?",
                    (definition.agent_id, int(row["idx"])),
                )
                updated += 1
                break
    if updated:
        logger.info("Backfilled %s agentruntime local_agent_id value(s)", updated)


def _migrate_agentruntime_type_unique(connection: sqlite3.Connection) -> None:
    tables = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "agentruntime" not in tables:
        return

    index_rows = connection.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='agentruntime'"
    ).fetchall()
    has_type_agent_unique = any(
        row["sql"]
        and "type" in str(row["sql"]).lower()
        and "agent_id" in str(row["sql"]).lower()
        for row in index_rows
    )
    if has_type_agent_unique:
        return

    table_sql_row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='agentruntime'"
    ).fetchone()
    table_sql = str(table_sql_row["sql"] or "") if table_sql_row else ""
    table_sql_lower = table_sql.lower()
    if (
        "unique" in table_sql_lower
        and "type" in table_sql_lower
        and "agent_id" in table_sql_lower
    ):
        connection.execute("DROP TABLE IF EXISTS agentruntime_legacy")
        return
    if "UNIQUE" not in table_sql.upper() or "agent_id" not in table_sql:
        return

    connection.execute("DROP TABLE IF EXISTS agentruntime_legacy")
    logger.info("Migrating agentruntime table: UNIQUE(agent_id) -> UNIQUE(type, agent_id)")
    connection.execute("ALTER TABLE agentruntime RENAME TO agentruntime_legacy")
    connection.execute(
        """
        CREATE TABLE agentruntime (
            idx INTEGER PRIMARY KEY AUTOINCREMENT,
            type INTEGER NOT NULL,
            token_url VARCHAR(200) NOT NULL,
            agent_url VARCHAR(200) NOT NULL,
            agent_name VARCHAR(50) NOT NULL,
            agent_id VARCHAR(50) NOT NULL,
            local_agent_id VARCHAR(50) NOT NULL DEFAULT '',
            description VARCHAR(255) NOT NULL,
            registered_date TEXT NOT NULL,
            service_id VARCHAR(20) NOT NULL,
            UNIQUE(type, agent_id)
        )
        """
    )
    connection.execute(
        """
        INSERT INTO agentruntime (
            idx, type, token_url, agent_url, agent_name, agent_id, local_agent_id,
            description, registered_date, service_id
        )
        SELECT
            idx, type, token_url, agent_url, agent_name, agent_id, local_agent_id,
            description, registered_date, service_id
        FROM agentruntime_legacy
        """
    )
    connection.execute("DROP TABLE agentruntime_legacy")
    logger.info("agentruntime unique constraint migration complete")


def _migrate_agentruntime_drop_url_columns(connection: sqlite3.Connection) -> None:
    tables = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "agentruntime" not in tables:
        return

    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(agentruntime)").fetchall()
    }
    if "token_url" not in columns and "agent_url" not in columns:
        return

    logger.info("Migrating agentruntime table: drop token_url and agent_url columns")
    connection.execute("DROP TABLE IF EXISTS agentruntime_legacy")
    connection.execute("ALTER TABLE agentruntime RENAME TO agentruntime_legacy")
    connection.execute(
        """
        CREATE TABLE agentruntime (
            idx INTEGER PRIMARY KEY AUTOINCREMENT,
            type INTEGER NOT NULL,
            agent_name VARCHAR(50) NOT NULL,
            agent_id VARCHAR(50) NOT NULL,
            local_agent_id VARCHAR(50) NOT NULL DEFAULT '',
            description VARCHAR(255) NOT NULL,
            registered_date TEXT NOT NULL,
            service_id VARCHAR(20) NOT NULL,
            UNIQUE(type, agent_id)
        )
        """
    )
    connection.execute(
        """
        INSERT INTO agentruntime (
            idx, type, agent_name, agent_id, local_agent_id,
            description, registered_date, service_id
        )
        SELECT
            idx, type, agent_name, agent_id, local_agent_id,
            description, registered_date, service_id
        FROM agentruntime_legacy
        """
    )
    connection.execute("DROP TABLE agentruntime_legacy")
    logger.info("agentruntime URL column migration complete")


def _migrate_agentruntime_talkable(connection: sqlite3.Connection) -> None:
    tables = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "agentruntime" not in tables:
        return

    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(agentruntime)").fetchall()
    }
    if "talkable" not in columns:
        connection.execute(
            "ALTER TABLE agentruntime ADD COLUMN talkable INTEGER NOT NULL DEFAULT 1"
        )
        logger.info("Added agentruntime.talkable column")
    else:
        return

    from backend.app.db.agentruntime import NON_TALKABLE_LOCAL_AGENT_IDS

    placeholders = ", ".join("?" for _ in NON_TALKABLE_LOCAL_AGENT_IDS)
    connection.execute(
        f"""
        UPDATE agentruntime
        SET talkable = 0
        WHERE local_agent_id IN ({placeholders})
        """,
        tuple(NON_TALKABLE_LOCAL_AGENT_IDS),
    )
    connection.execute(
        f"""
        UPDATE agentruntime
        SET talkable = 1
        WHERE local_agent_id NOT IN ({placeholders})
           OR local_agent_id IS NULL
           OR TRIM(local_agent_id) = ''
        """,
        tuple(NON_TALKABLE_LOCAL_AGENT_IDS),
    )
    logger.info("Backfilled agentruntime.talkable flags for new column")


def _migrate_agentruntime_is_orchestrator(connection: sqlite3.Connection) -> None:
    tables = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "agentruntime" not in tables:
        return

    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(agentruntime)").fetchall()
    }
    if "is_orchestrator" not in columns:
        connection.execute(
            "ALTER TABLE agentruntime ADD COLUMN is_orchestrator INTEGER NOT NULL DEFAULT 0"
        )
        logger.info("Added agentruntime.is_orchestrator column")
    else:
        return

    from backend.app.db.agentruntime import ORCHESTRATOR_LOCAL_AGENT_IDS

    placeholders = ", ".join("?" for _ in ORCHESTRATOR_LOCAL_AGENT_IDS)
    connection.execute(
        f"""
        UPDATE agentruntime
        SET is_orchestrator = 1
        WHERE local_agent_id IN ({placeholders})
        """,
        tuple(ORCHESTRATOR_LOCAL_AGENT_IDS),
    )
    connection.execute(
        f"""
        UPDATE agentruntime
        SET is_orchestrator = 0
        WHERE local_agent_id NOT IN ({placeholders})
           OR local_agent_id IS NULL
           OR TRIM(local_agent_id) = ''
        """,
        tuple(ORCHESTRATOR_LOCAL_AGENT_IDS),
    )
    logger.info("Backfilled agentruntime.is_orchestrator flags for new column")


def _ensure_jobs_table(connection: sqlite3.Connection) -> None:
    tables = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "jobs" in tables:
        return

    connection.execute(
        """
        CREATE TABLE jobs (
            idx INTEGER PRIMARY KEY AUTOINCREMENT,
            srnum VARCHAR(20) NOT NULL UNIQUE,
            status_code INTEGER NOT NULL DEFAULT 0,
            approver_registered_date TEXT,
            approver VARCHAR(20),
            job_title VARCHAR(300) NOT NULL,
            requester_name VARCHAR(100) NOT NULL,
            requester_email VARCHAR(100) NOT NULL,
            requester_depart VARCHAR(100) NOT NULL,
            job_content TEXT NOT NULL,
            request_date TEXT NOT NULL,
            madang_id VARCHAR(50) NOT NULL,
            team_id VARCHAR(50) NOT NULL,
            channel_id VARCHAR(120) NOT NULL,
            message_id VARCHAR(50) NOT NULL,
            received_at TEXT NOT NULL
        )
        """
    )
    logger.info("Created jobs table")


def _migrate_jobs_approver_column(connection: sqlite3.Connection) -> None:
    tables = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "jobs" not in tables:
        return

    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
    }
    if "approver" in columns:
        return

    connection.execute("ALTER TABLE jobs ADD COLUMN approver VARCHAR(20)")
    logger.info("Added jobs.approver column")


def _ensure_jobs_result_table(connection: sqlite3.Connection) -> None:
    tables = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "jobs_result" in tables:
        return

    connection.execute(
        """
        CREATE TABLE jobs_result (
            srnum VARCHAR(20) NOT NULL PRIMARY KEY,
            result TEXT NOT NULL,
            complete_date TEXT NOT NULL
        )
        """
    )
    logger.info("Created jobs_result table")


def _ensure_mynotes_table(connection: sqlite3.Connection) -> None:
    tables = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "mynotes" in tables:
        return

    connection.execute(
        """
        CREATE TABLE mynotes (
            idx INTEGER PRIMARY KEY AUTOINCREMENT,
            userid VARCHAR(50) NOT NULL,
            note_name VARCHAR(50) NOT NULL,
            create_date TEXT NOT NULL,
            origin_file VARCHAR(200) NOT NULL,
            last_update TEXT NOT NULL
        )
        """
    )
    logger.info("Created mynotes table")


def _drop_legacy_product_tables(connection: sqlite3.Connection) -> None:
    for table_name in ("job_notifications", "inventory", "agents"):
        connection.execute(f"DROP TABLE IF EXISTS {table_name}")


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


def init_database(database_path: str | Path | None = None) -> Path:
    path = resolve_database_path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with get_connection(path) as connection:
        _apply_schema(connection)
        _apply_migrations(connection)
        connection.commit()
        seed_initial_users(connection)

    logger.info("SQLite database initialized at %s", path)
    return path
