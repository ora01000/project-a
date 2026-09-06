"""work_node / workflow tables for the designer screen."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from backend.app.db.database import get_connection
from backend.app.db.job_datetime import now_job_datetime

SCRIPT_TYPES = frozenset({"yaml", "ansible", "cli"})

_WORK_NODE_SELECT = """
    idx, uuid, work_name, work_description, target_agent, work_script,
    script_type, test_result, files, create_date, validate_date
"""

_WORKFLOW_SELECT = """
    idx, uuid, checkin_user, checkin_time, workflow_name, workflow_description, workflow,
    create_date, test_result, validate_date
"""


def normalize_script_type(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if not normalized:
        return ""
    if normalized not in SCRIPT_TYPES:
        raise ValueError("script_type은 yaml, ansible, cli 중 하나여야 합니다.")
    return normalized


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _backfill_missing_uuids(connection, table: str) -> None:
    rows = connection.execute(
        f"SELECT idx FROM {table} WHERE uuid IS NULL OR btrim(COALESCE(uuid, '')) = ''"
    ).fetchall()
    for row in rows:
        connection.execute(
            f"UPDATE {table} SET uuid = ? WHERE idx = ?",
            (_new_uuid(), int(row["idx"])),
        )


def _ensure_uuid_unique_index(connection, table: str, index_name: str) -> None:
    _backfill_missing_uuids(connection, table)
    connection.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {table} (uuid)")


def _work_node_column_names(connection) -> set[str]:
    rows = connection.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'work_node'
        """
    ).fetchall()
    names: set[str] = set()
    for row in rows:
        if hasattr(row, "keys"):
            names.add(str(row["column_name"]).lower())
        else:
            names.add(str(row[0]).lower())
    return names


def _migrate_work_node_script_columns(connection) -> None:
    connection.execute(
        """
        ALTER TABLE work_node
            ADD COLUMN IF NOT EXISTS work_script TEXT NOT NULL DEFAULT ''
        """
    )
    columns = _work_node_column_names(connection)
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
            idx BIGSERIAL PRIMARY KEY,
            uuid VARCHAR(36) NOT NULL UNIQUE,
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
    _ensure_uuid_unique_index(connection, "work_node", "work_node_uuid_uidx")

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow (
            idx BIGSERIAL PRIMARY KEY,
            uuid VARCHAR(36) NOT NULL UNIQUE,
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
    _ensure_uuid_unique_index(connection, "workflow", "workflow_uuid_uidx")


@dataclass(frozen=True)
class WorkNodeRecord:
    idx: int
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
    idx: int
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
    node_uuid = row["uuid"] if "uuid" in keys else ""
    description = row["work_description"] if "work_description" in keys else ""
    script_type = row["script_type"] if "script_type" in keys else ""
    create_date = row["create_date"] if "create_date" in keys else ""
    validate_date = row["validate_date"] if "validate_date" in keys else ""
    return WorkNodeRecord(
        idx=int(row["idx"]),
        uuid=str(node_uuid or ""),
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
    workflow_uuid = row["uuid"] if "uuid" in keys else ""
    checkin_user = row["checkin_user"] if "checkin_user" in keys else 0
    checkin_time = row["checkin_time"] if "checkin_time" in keys else ""
    create_date = row["create_date"] if "create_date" in keys else ""
    validate_date = row["validate_date"] if "validate_date" in keys else ""
    test_result = row["test_result"] if "test_result" in keys else 0
    return WorkflowRecord(
        idx=int(row["idx"]),
        uuid=str(workflow_uuid or ""),
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
            f"SELECT {_WORK_NODE_SELECT} FROM work_node ORDER BY idx ASC"
        ).fetchall()
    return [_row_to_work_node(row) for row in rows]


def get_work_node_by_idx(database_path: str | Path, idx: int) -> WorkNodeRecord | None:
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        row = connection.execute(
            f"SELECT {_WORK_NODE_SELECT} FROM work_node WHERE idx = ?",
            (idx,),
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
) -> WorkNodeRecord:
    created_at = now_job_datetime()
    validate_at = created_at if test_result else ""
    normalized_script_type = normalize_script_type(script_type)
    node_uuid = _new_uuid()
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
    idx: int,
    *,
    work_name: str,
    work_description: str,
    target_agent: int,
    work_script: str,
    script_type: str,
    test_result: bool,
    files: str,
) -> WorkNodeRecord | None:
    existing = get_work_node_by_idx(database_path, idx)
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
            WHERE idx = ?
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
                idx,
            ),
        )
    return get_work_node_by_idx(database_path, idx)


def delete_work_node(database_path: str | Path, idx: int) -> bool:
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        cursor = connection.execute("DELETE FROM work_node WHERE idx = ?", (idx,))
        return int(cursor.rowcount or 0) > 0


def list_workflows(database_path: str | Path) -> list[WorkflowRecord]:
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        rows = connection.execute(
            f"SELECT {_WORKFLOW_SELECT} FROM workflow ORDER BY idx DESC"
        ).fetchall()
    return [_row_to_workflow(row) for row in rows]


def get_workflow_by_idx(database_path: str | Path, idx: int) -> WorkflowRecord | None:
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        row = connection.execute(
            f"SELECT {_WORKFLOW_SELECT} FROM workflow WHERE idx = ?",
            (idx,),
        ).fetchone()
    return _row_to_workflow(row) if row else None


def create_workflow(
    database_path: str | Path,
    *,
    workflow_name: str,
    workflow_description: str = "",
    workflow: str = "",
    checkin_user: int = 0,
) -> WorkflowRecord:
    created_at = now_job_datetime()
    workflow_uuid = _new_uuid()
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
    idx: int,
    *,
    workflow_name: str,
    workflow_description: str,
    workflow: str,
    checkin_user: int | None = None,
) -> WorkflowRecord | None:
    existing = get_workflow_by_idx(database_path, idx)
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
            WHERE idx = ?
            """,
            (
                workflow_name.strip(),
                (workflow_description or "").strip()[:500],
                (workflow or "").strip(),
                next_checkin,
                next_checkin_time,
                idx,
            ),
        )
    return get_workflow_by_idx(database_path, idx)


def set_workflow_checkin_user(
    database_path: str | Path,
    idx: int,
    checkin_user: int,
) -> WorkflowRecord | None:
    existing = get_workflow_by_idx(database_path, idx)
    if existing is None:
        return None
    next_checkin = int(checkin_user)
    checkin_time = now_job_datetime() if next_checkin > 0 else ""
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        connection.execute(
            "UPDATE workflow SET checkin_user = ?, checkin_time = ? WHERE idx = ?",
            (next_checkin, checkin_time, idx),
        )
    return get_workflow_by_idx(database_path, idx)


def delete_workflow(database_path: str | Path, idx: int) -> bool:
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        cursor = connection.execute("DELETE FROM workflow WHERE idx = ?", (idx,))
        return int(cursor.rowcount or 0) > 0
