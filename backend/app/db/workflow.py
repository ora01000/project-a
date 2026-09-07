"""work_node / workflow tables for the designer screen."""

from __future__ import annotations

import re
import uuid as uuid_lib
from dataclasses import dataclass
from pathlib import Path

from backend.app.db.database import get_connection
from backend.app.db.job_datetime import now_job_datetime

SCRIPT_TYPES = frozenset({"yaml", "ansible", "cli"})

_WORK_NODE_SELECT = """
    uuid, work_name, work_description, target_agent, work_script,
    script_type, test_result, files, create_date, validate_date
"""

_WORKFLOW_SELECT = """
    uuid, checkin_user, checkin_time, workflow_name, workflow_description, workflow,
    create_date, test_result, validate_date
"""


def normalize_script_type(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if not normalized:
        return ""
    if normalized not in SCRIPT_TYPES:
        raise ValueError("script_type은 yaml, ansible, cli 중 하나여야 합니다.")
    return normalized


_UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _new_uuid() -> str:
    return str(uuid_lib.uuid4())


def _normalize_uuid(value: str | None) -> str:
    """Accept a caller-supplied uuid (AI import) or mint a new one.

    Rejects malformed ids up front: flow expressions only resolve tokens that
    match the uuid shape, so anything else would be unreachable once stored.
    """
    text = (value or "").strip()
    if not text:
        return _new_uuid()
    if not _UUID_PATTERN.match(text):
        raise ValueError(f"uuid 형식이 올바르지 않습니다: {text}")
    return text.lower()


def _column_value(row, name: str, index: int = 0):
    if hasattr(row, "keys"):
        return row[name]
    return row[index]


def _table_column_names(connection, table: str) -> set[str]:
    rows = connection.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = ?
        """,
        (table,),
    ).fetchall()
    return {str(_column_value(row, "column_name")).lower() for row in rows}


def _primary_key_columns(connection, table: str) -> set[str]:
    rows = connection.execute(
        """
        SELECT a.attname AS column_name
        FROM pg_index i
        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY (i.indkey)
        WHERE i.indrelid = to_regclass(?) AND i.indisprimary
        """,
        (table,),
    ).fetchall()
    return {str(_column_value(row, "column_name")).lower() for row in rows}


def _backfill_missing_uuids(connection, table: str) -> None:
    """Give every row a uuid before it becomes the primary key.

    ``ctid`` is used as the row handle so this works both before and after the
    legacy ``idx`` column is dropped.
    """
    rows = connection.execute(
        f"""
        SELECT ctid::text AS row_id
        FROM {table}
        WHERE uuid IS NULL OR btrim(COALESCE(uuid, '')) = ''
        """
    ).fetchall()
    for row in rows:
        connection.execute(
            f"UPDATE {table} SET uuid = ? WHERE ctid = ?::tid",
            (_new_uuid(), str(_column_value(row, "row_id"))),
        )


def rewrite_expression_idx_to_uuid(expression: str, mapping: dict[str, str]) -> str:
    """Replace legacy integer work_node tokens with their uuid equivalents.

    Only used while migrating stored ``workflow.workflow`` expressions; the
    runtime parser accepts uuid tokens exclusively.
    """
    text = (expression or "").strip()
    if not text:
        return ""
    rewritten: list[str] = []
    for part in text.split("->"):
        token = part.strip()
        upper = token.upper()
        if upper in {"S", "E"} or upper.startswith("H:"):
            rewritten.append(token)
            continue
        if ":" in token:
            left, right = token.split(":", 1)
            left = left.strip()
            right = right.strip()
            fail = right if right.upper() == "E" else mapping.get(right, right)
            rewritten.append(f"{mapping.get(left, left)}:{fail}")
            continue
        rewritten.append(mapping.get(token, token))
    return "->".join(rewritten)


def _migrate_workflow_expressions_to_uuid(connection) -> None:
    rows = connection.execute("SELECT idx, uuid FROM work_node").fetchall()
    mapping = {
        str(_column_value(row, "idx", 0)): str(_column_value(row, "uuid", 1))
        for row in rows
        if str(_column_value(row, "uuid", 1) or "").strip()
    }
    if not mapping:
        return
    for row in connection.execute("SELECT uuid, workflow FROM workflow").fetchall():
        current = str(_column_value(row, "workflow", 1) or "")
        rewritten = rewrite_expression_idx_to_uuid(current, mapping)
        if rewritten == current.strip():
            continue
        connection.execute(
            "UPDATE workflow SET workflow = ? WHERE uuid = ?",
            (rewritten, str(_column_value(row, "uuid", 0))),
        )


def _migrate_to_uuid_primary_key(connection, table: str) -> None:
    if _primary_key_columns(connection, table) == {"uuid"}:
        return
    # Dropping the BIGSERIAL column also drops the old primary key and sequence.
    connection.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS idx")
    connection.execute(f"ALTER TABLE {table} ALTER COLUMN uuid SET NOT NULL")
    connection.execute(f"ALTER TABLE {table} ALTER COLUMN uuid DROP DEFAULT")
    connection.execute(f"ALTER TABLE {table} ADD PRIMARY KEY (uuid)")
    # The primary key index supersedes the legacy uniqueness helpers.
    connection.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_uuid_key")
    connection.execute(f"DROP INDEX IF EXISTS {table}_uuid_uidx")


def _migrate_work_node_script_columns(connection) -> None:
    connection.execute(
        """
        ALTER TABLE work_node
            ADD COLUMN IF NOT EXISTS work_script TEXT NOT NULL DEFAULT ''
        """
    )
    columns = _table_column_names(connection, "work_node")
    if "agent_response" in columns:
        connection.execute(
            """
            UPDATE work_node
            SET work_script = agent_response
            WHERE btrim(COALESCE(work_script, '')) = ''
              AND btrim(COALESCE(agent_response, '')) <> ''
            """
        )
        connection.execute("ALTER TABLE work_node DROP COLUMN IF EXISTS agent_response")
    if "user_prompt" in columns:
        connection.execute("ALTER TABLE work_node DROP COLUMN IF EXISTS user_prompt")


def ensure_workflow_tables(connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS work_node (
            uuid VARCHAR(36) PRIMARY KEY,
            work_name VARCHAR(100) NOT NULL,
            work_description VARCHAR(500) NOT NULL DEFAULT '',
            target_agent INTEGER NOT NULL DEFAULT 0,
            work_script TEXT NOT NULL DEFAULT '',
            script_type VARCHAR(20) NOT NULL DEFAULT '',
            test_result INTEGER NOT NULL DEFAULT 0,
            files VARCHAR(300) NOT NULL DEFAULT '',
            create_date TEXT NOT NULL DEFAULT '',
            validate_date TEXT NOT NULL DEFAULT ''
        )
        """
    )
    connection.execute(
        """
        ALTER TABLE work_node
            ADD COLUMN IF NOT EXISTS uuid VARCHAR(36) NOT NULL DEFAULT ''
        """
    )
    connection.execute(
        """
        ALTER TABLE work_node
            ADD COLUMN IF NOT EXISTS work_description VARCHAR(500) NOT NULL DEFAULT ''
        """
    )
    connection.execute(
        """
        ALTER TABLE work_node
            ADD COLUMN IF NOT EXISTS script_type VARCHAR(20) NOT NULL DEFAULT ''
        """
    )
    connection.execute(
        """
        ALTER TABLE work_node
            ADD COLUMN IF NOT EXISTS create_date TEXT NOT NULL DEFAULT ''
        """
    )
    connection.execute(
        """
        ALTER TABLE work_node
            ADD COLUMN IF NOT EXISTS validate_date TEXT NOT NULL DEFAULT ''
        """
    )
    _migrate_work_node_script_columns(connection)

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow (
            uuid VARCHAR(36) PRIMARY KEY,
            checkin_user INTEGER NOT NULL DEFAULT 0,
            checkin_time TEXT NOT NULL DEFAULT '',
            workflow_name VARCHAR(100) NOT NULL,
            workflow_description VARCHAR(500) NOT NULL DEFAULT '',
            workflow TEXT NOT NULL DEFAULT '',
            create_date TEXT NOT NULL DEFAULT '',
            test_result INTEGER NOT NULL DEFAULT 0,
            validate_date TEXT NOT NULL DEFAULT ''
        )
        """
    )
    connection.execute(
        """
        ALTER TABLE workflow
            ADD COLUMN IF NOT EXISTS uuid VARCHAR(36) NOT NULL DEFAULT ''
        """
    )
    connection.execute(
        """
        ALTER TABLE workflow
            ADD COLUMN IF NOT EXISTS checkin_user INTEGER NOT NULL DEFAULT 0
        """
    )
    connection.execute(
        """
        ALTER TABLE workflow
            ADD COLUMN IF NOT EXISTS checkin_time TEXT NOT NULL DEFAULT ''
        """
    )
    connection.execute(
        """
        ALTER TABLE workflow
            ADD COLUMN IF NOT EXISTS create_date TEXT NOT NULL DEFAULT ''
        """
    )
    connection.execute(
        """
        ALTER TABLE workflow
            ADD COLUMN IF NOT EXISTS test_result INTEGER NOT NULL DEFAULT 0
        """
    )
    connection.execute(
        """
        ALTER TABLE workflow
            ADD COLUMN IF NOT EXISTS validate_date TEXT NOT NULL DEFAULT ''
        """
    )

    _backfill_missing_uuids(connection, "work_node")
    _backfill_missing_uuids(connection, "workflow")
    if "idx" in _table_column_names(connection, "work_node"):
        # Expressions still reference integer work_node ids; remap before the
        # mapping source disappears with the idx column.
        _migrate_workflow_expressions_to_uuid(connection)
    _migrate_to_uuid_primary_key(connection, "work_node")
    _migrate_to_uuid_primary_key(connection, "workflow")


@dataclass(frozen=True)
class WorkNodeRecord:
    uuid: str
    work_name: str
    work_description: str
    target_agent: int
    work_script: str
    script_type: str
    test_result: bool
    files: str
    create_date: str
    validate_date: str


@dataclass(frozen=True)
class WorkflowRecord:
    uuid: str
    checkin_user: int
    checkin_time: str
    workflow_name: str
    workflow_description: str
    workflow: str
    create_date: str
    test_result: bool
    validate_date: str


def _row_to_work_node(row) -> WorkNodeRecord:
    keys = row.keys() if hasattr(row, "keys") else []
    description = row["work_description"] if "work_description" in keys else ""
    script_type = row["script_type"] if "script_type" in keys else ""
    create_date = row["create_date"] if "create_date" in keys else ""
    validate_date = row["validate_date"] if "validate_date" in keys else ""
    return WorkNodeRecord(
        uuid=str(row["uuid"] or ""),
        work_name=str(row["work_name"] or ""),
        work_description=str(description or ""),
        target_agent=int(row["target_agent"] or 0),
        work_script=str(row["work_script"] or ""),
        script_type=str(script_type or "").strip().lower(),
        test_result=bool(int(row["test_result"] or 0)),
        files=str(row["files"] or ""),
        create_date=str(create_date or ""),
        validate_date=str(validate_date or ""),
    )


def _row_to_workflow(row) -> WorkflowRecord:
    keys = row.keys() if hasattr(row, "keys") else []
    checkin_user = row["checkin_user"] if "checkin_user" in keys else 0
    checkin_time = row["checkin_time"] if "checkin_time" in keys else ""
    create_date = row["create_date"] if "create_date" in keys else ""
    validate_date = row["validate_date"] if "validate_date" in keys else ""
    test_result = row["test_result"] if "test_result" in keys else 0
    return WorkflowRecord(
        uuid=str(row["uuid"] or ""),
        checkin_user=int(checkin_user or 0),
        checkin_time=str(checkin_time or ""),
        workflow_name=str(row["workflow_name"] or ""),
        workflow_description=str(row["workflow_description"] or ""),
        workflow=str(row["workflow"] or ""),
        create_date=str(create_date or ""),
        test_result=bool(int(test_result or 0)),
        validate_date=str(validate_date or ""),
    )


def list_work_nodes(database_path: str | Path) -> list[WorkNodeRecord]:
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        rows = connection.execute(
            f"SELECT {_WORK_NODE_SELECT} FROM work_node ORDER BY create_date ASC, uuid ASC"
        ).fetchall()
    return [_row_to_work_node(row) for row in rows]


def get_work_node_by_uuid(database_path: str | Path, node_uuid: str) -> WorkNodeRecord | None:
    key = (node_uuid or "").strip()
    if not key:
        return None
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        row = connection.execute(
            f"SELECT {_WORK_NODE_SELECT} FROM work_node WHERE uuid = ?",
            (key,),
        ).fetchone()
    return _row_to_work_node(row) if row else None


def create_work_node(
    database_path: str | Path,
    *,
    work_name: str,
    target_agent: int = 0,
    work_description: str = "",
    work_script: str = "",
    script_type: str = "",
    test_result: bool = False,
    files: str = "",
    uuid: str | None = None,
) -> WorkNodeRecord:
    created_at = now_job_datetime()
    validate_at = created_at if test_result else ""
    normalized_script_type = normalize_script_type(script_type)
    node_uuid = _normalize_uuid(uuid)
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        row = connection.execute(
            f"""
            INSERT INTO work_node (
                uuid, work_name, work_description, target_agent, work_script,
                script_type, test_result, files, create_date, validate_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING {_WORK_NODE_SELECT}
            """,
            (
                node_uuid,
                work_name.strip() or "새 작업노드",
                (work_description or "").strip()[:500],
                int(target_agent),
                work_script or "",
                normalized_script_type,
                1 if test_result else 0,
                (files or "").strip()[:300],
                created_at,
                validate_at,
            ),
        ).fetchone()
    return _row_to_work_node(row)


def update_work_node(
    database_path: str | Path,
    node_uuid: str,
    *,
    work_name: str,
    work_description: str,
    target_agent: int,
    work_script: str,
    script_type: str,
    test_result: bool,
    files: str,
) -> WorkNodeRecord | None:
    existing = get_work_node_by_uuid(database_path, node_uuid)
    if existing is None:
        return None
    if test_result:
        validate_date = existing.validate_date or now_job_datetime()
    else:
        validate_date = ""
    normalized_script_type = normalize_script_type(script_type)
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        connection.execute(
            """
            UPDATE work_node
            SET work_name = ?, work_description = ?, target_agent = ?, work_script = ?,
                script_type = ?, test_result = ?, files = ?, validate_date = ?
            WHERE uuid = ?
            """,
            (
                work_name.strip() or "새 작업노드",
                (work_description or "").strip()[:500],
                int(target_agent),
                work_script or "",
                normalized_script_type,
                1 if test_result else 0,
                (files or "").strip()[:300],
                validate_date,
                existing.uuid,
            ),
        )
    return get_work_node_by_uuid(database_path, existing.uuid)


def delete_work_node(database_path: str | Path, node_uuid: str) -> bool:
    key = (node_uuid or "").strip()
    if not key:
        return False
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        cursor = connection.execute("DELETE FROM work_node WHERE uuid = ?", (key,))
        return int(cursor.rowcount or 0) > 0


def list_workflows(database_path: str | Path) -> list[WorkflowRecord]:
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        rows = connection.execute(
            f"SELECT {_WORKFLOW_SELECT} FROM workflow ORDER BY create_date DESC, uuid DESC"
        ).fetchall()
    return [_row_to_workflow(row) for row in rows]


def get_workflow_by_uuid(database_path: str | Path, workflow_uuid: str) -> WorkflowRecord | None:
    key = (workflow_uuid or "").strip()
    if not key:
        return None
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        row = connection.execute(
            f"SELECT {_WORKFLOW_SELECT} FROM workflow WHERE uuid = ?",
            (key,),
        ).fetchone()
    return _row_to_workflow(row) if row else None


def create_workflow(
    database_path: str | Path,
    *,
    workflow_name: str,
    workflow_description: str = "",
    workflow: str = "",
    checkin_user: int = 0,
    uuid: str | None = None,
) -> WorkflowRecord:
    created_at = now_job_datetime()
    workflow_uuid = _normalize_uuid(uuid)
    next_checkin = int(checkin_user or 0)
    checkin_time = now_job_datetime() if next_checkin > 0 else ""
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        row = connection.execute(
            f"""
            INSERT INTO workflow (
                uuid, checkin_user, checkin_time, workflow_name, workflow_description, workflow,
                create_date, test_result, validate_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, '')
            RETURNING {_WORKFLOW_SELECT}
            """,
            (
                workflow_uuid,
                next_checkin,
                checkin_time,
                workflow_name.strip(),
                (workflow_description or "").strip()[:500],
                (workflow or "").strip(),
                created_at,
            ),
        ).fetchone()
    return _row_to_workflow(row)


def update_workflow(
    database_path: str | Path,
    workflow_uuid: str,
    *,
    workflow_name: str,
    workflow_description: str,
    workflow: str,
    checkin_user: int | None = None,
) -> WorkflowRecord | None:
    existing = get_workflow_by_uuid(database_path, workflow_uuid)
    if existing is None:
        return None
    if checkin_user is None:
        next_checkin = existing.checkin_user
        next_checkin_time = existing.checkin_time
    else:
        next_checkin = int(checkin_user)
        if next_checkin > 0:
            next_checkin_time = existing.checkin_time or now_job_datetime()
            if next_checkin != existing.checkin_user:
                next_checkin_time = now_job_datetime()
        else:
            next_checkin_time = ""
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        connection.execute(
            """
            UPDATE workflow
            SET workflow_name = ?, workflow_description = ?, workflow = ?,
                checkin_user = ?, checkin_time = ?
            WHERE uuid = ?
            """,
            (
                workflow_name.strip(),
                (workflow_description or "").strip()[:500],
                (workflow or "").strip(),
                next_checkin,
                next_checkin_time,
                existing.uuid,
            ),
        )
    return get_workflow_by_uuid(database_path, existing.uuid)


def set_workflow_checkin_user(
    database_path: str | Path,
    workflow_uuid: str,
    checkin_user: int,
) -> WorkflowRecord | None:
    existing = get_workflow_by_uuid(database_path, workflow_uuid)
    if existing is None:
        return None
    next_checkin = int(checkin_user)
    checkin_time = now_job_datetime() if next_checkin > 0 else ""
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        connection.execute(
            "UPDATE workflow SET checkin_user = ?, checkin_time = ? WHERE uuid = ?",
            (next_checkin, checkin_time, existing.uuid),
        )
    return get_workflow_by_uuid(database_path, existing.uuid)


def delete_workflow(database_path: str | Path, workflow_uuid: str) -> bool:
    key = (workflow_uuid or "").strip()
    if not key:
        return False
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        cursor = connection.execute("DELETE FROM workflow WHERE uuid = ?", (key,))
        return int(cursor.rowcount or 0) > 0
