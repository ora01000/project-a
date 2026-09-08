"""work_node / workflow tables for the designer screen."""

from __future__ import annotations

import re
import shutil
import uuid as uuid_lib
from dataclasses import dataclass
from pathlib import Path

from backend.app.config import work_node_upload_dir
from backend.app.db.database import get_connection
from backend.app.db.job_datetime import now_job_datetime
from backend.app.services.workflow_graph import parse_workflow_tokens

SCRIPT_TYPES = frozenset({"kubectl", "ansible", "cli", "prompt"})

_WORK_NODE_SELECT = """
    uuid, owner, work_name, work_description, target_agent, work_script,
    script_type, test_result, files, create_date, validate_date,
    last_start_date, last_end_date, last_success, last_fail_reason,
    use_previous_work_result, work_report
"""

_WORKFLOW_SELECT = """
    uuid, owner, distribute, workflow_name, workflow_description, workflow,
    create_date, test_result, validate_date,
    last_start_date, last_end_date, run_count, sucess_count, fail_count, last_success
"""


def normalize_script_type(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if not normalized:
        return ""
    # Legacy alias from earlier schema drafts.
    if normalized == "yaml":
        normalized = "kubectl"
    if normalized not in SCRIPT_TYPES:
        raise ValueError("script_type은 kubectl, ansible, cli, prompt 중 하나여야 합니다.")
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


def work_uuids_from_expression(expression: str) -> set[str]:
    """Collect work_node uuids referenced by a workflow expression."""
    uuids: set[str] = set()
    try:
        tokens = parse_workflow_tokens(expression)
    except ValueError:
        return uuids
    for token in tokens:
        if token.work_uuid:
            uuids.add(str(token.work_uuid))
        if token.fail_work_uuid:
            uuids.add(str(token.fail_work_uuid))
    return uuids


def rewrite_expression_uuid_map(expression: str, mapping: dict[str, str]) -> str:
    """Remap work_node uuid tokens in a workflow expression."""
    text = (expression or "").strip()
    if not text or not mapping:
        return text
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


def rewrite_expression_idx_to_uuid(expression: str, mapping: dict[str, str]) -> str:
    """Replace legacy integer work_node tokens with their uuid equivalents.

    Only used while migrating stored ``workflow.workflow`` expressions; the
    runtime parser accepts uuid tokens exclusively.
    """
    return rewrite_expression_uuid_map(expression, mapping)


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
            owner INTEGER NOT NULL DEFAULT 1,
            work_name VARCHAR(100) NOT NULL,
            work_description VARCHAR(500) NOT NULL DEFAULT '',
            target_agent INTEGER NOT NULL DEFAULT 0,
            work_script TEXT NOT NULL DEFAULT '',
            script_type VARCHAR(20) NOT NULL DEFAULT '',
            test_result INTEGER NOT NULL DEFAULT 0,
            files VARCHAR(300) NOT NULL DEFAULT '',
            create_date TEXT NOT NULL DEFAULT '',
            validate_date TEXT NOT NULL DEFAULT '',
            last_start_date TEXT NOT NULL DEFAULT '',
            last_end_date TEXT NOT NULL DEFAULT '',
            last_success INTEGER NOT NULL DEFAULT 0,
            last_fail_reason VARCHAR(200) NOT NULL DEFAULT '',
            use_previous_work_result INTEGER NOT NULL DEFAULT 0,
            work_report VARCHAR(200) NOT NULL DEFAULT ''
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
            ADD COLUMN IF NOT EXISTS owner INTEGER NOT NULL DEFAULT 1
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
    connection.execute(
        """
        ALTER TABLE work_node
            ADD COLUMN IF NOT EXISTS last_start_date TEXT NOT NULL DEFAULT ''
        """
    )
    connection.execute(
        """
        ALTER TABLE work_node
            ADD COLUMN IF NOT EXISTS last_end_date TEXT NOT NULL DEFAULT ''
        """
    )
    connection.execute(
        """
        ALTER TABLE work_node
            ADD COLUMN IF NOT EXISTS last_success INTEGER NOT NULL DEFAULT 0
        """
    )
    connection.execute(
        """
        ALTER TABLE work_node
            ADD COLUMN IF NOT EXISTS last_fail_reason VARCHAR(200) NOT NULL DEFAULT ''
        """
    )
    connection.execute(
        """
        ALTER TABLE work_node
            ADD COLUMN IF NOT EXISTS use_previous_work_result INTEGER NOT NULL DEFAULT 0
        """
    )
    connection.execute(
        """
        ALTER TABLE work_node
            ADD COLUMN IF NOT EXISTS work_report VARCHAR(200) NOT NULL DEFAULT ''
        """
    )
    _migrate_work_node_script_columns(connection)

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow (
            uuid VARCHAR(36) PRIMARY KEY,
            owner INTEGER NOT NULL DEFAULT 1,
            distribute BOOLEAN NOT NULL DEFAULT FALSE,
            workflow_name VARCHAR(100) NOT NULL,
            workflow_description VARCHAR(500) NOT NULL DEFAULT '',
            workflow TEXT NOT NULL DEFAULT '',
            create_date TEXT NOT NULL DEFAULT '',
            test_result INTEGER NOT NULL DEFAULT 0,
            validate_date TEXT NOT NULL DEFAULT '',
            last_start_date TEXT NOT NULL DEFAULT '',
            last_end_date TEXT NOT NULL DEFAULT '',
            run_count INTEGER NOT NULL DEFAULT 0,
            sucess_count INTEGER NOT NULL DEFAULT 0,
            fail_count INTEGER NOT NULL DEFAULT 0,
            last_success INTEGER NOT NULL DEFAULT 0
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
            ADD COLUMN IF NOT EXISTS owner INTEGER NOT NULL DEFAULT 1
        """
    )
    connection.execute(
        """
        ALTER TABLE workflow
            ADD COLUMN IF NOT EXISTS distribute BOOLEAN NOT NULL DEFAULT FALSE
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
    connection.execute(
        """
        ALTER TABLE workflow
            ADD COLUMN IF NOT EXISTS last_start_date TEXT NOT NULL DEFAULT ''
        """
    )
    connection.execute(
        """
        ALTER TABLE workflow
            ADD COLUMN IF NOT EXISTS last_end_date TEXT NOT NULL DEFAULT ''
        """
    )
    connection.execute(
        """
        ALTER TABLE workflow
            ADD COLUMN IF NOT EXISTS run_count INTEGER NOT NULL DEFAULT 0
        """
    )
    connection.execute(
        """
        ALTER TABLE workflow
            ADD COLUMN IF NOT EXISTS sucess_count INTEGER NOT NULL DEFAULT 0
        """
    )
    connection.execute(
        """
        ALTER TABLE workflow
            ADD COLUMN IF NOT EXISTS fail_count INTEGER NOT NULL DEFAULT 0
        """
    )
    connection.execute(
        """
        ALTER TABLE workflow
            ADD COLUMN IF NOT EXISTS last_success INTEGER NOT NULL DEFAULT 0
        """
    )
    connection.execute("ALTER TABLE work_node ALTER COLUMN owner SET DEFAULT 1")
    connection.execute("ALTER TABLE workflow ALTER COLUMN owner SET DEFAULT 1")
    # Migrate away from checkin model when upgrading existing DBs.
    connection.execute("ALTER TABLE workflow DROP COLUMN IF EXISTS checkin_user")
    connection.execute("ALTER TABLE workflow DROP COLUMN IF EXISTS checkin_time")

    _backfill_missing_uuids(connection, "work_node")
    _backfill_missing_uuids(connection, "workflow")
    if "idx" in _table_column_names(connection, "work_node"):
        # Expressions still reference integer work_node ids; remap before the
        # mapping source disappears with the idx column.
        _migrate_workflow_expressions_to_uuid(connection)
    _migrate_to_uuid_primary_key(connection, "work_node")
    _migrate_to_uuid_primary_key(connection, "workflow")

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_history (
            idx SERIAL PRIMARY KEY,
            uuid VARCHAR(36) NOT NULL,
            start_date TEXT NOT NULL DEFAULT '',
            end_date TEXT NOT NULL DEFAULT '',
            finish_success INTEGER NOT NULL DEFAULT 0,
            result_file VARCHAR(1000) NOT NULL DEFAULT '',
            user_idx INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    connection.execute(
        """
        ALTER TABLE workflow_history
            ADD COLUMN IF NOT EXISTS user_idx INTEGER NOT NULL DEFAULT 1
        """
    )
    connection.execute(
        """
        UPDATE workflow_history
        SET user_idx = 1
        WHERE user_idx IS NULL OR user_idx <= 0
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_history_uuid
            ON workflow_history (uuid)
        """
    )


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
    last_start_date: str = ""
    last_end_date: str = ""
    last_success: bool = False
    last_fail_reason: str = ""
    use_previous_work_result: bool = False
    work_report: str = ""
    owner: int = 0


@dataclass(frozen=True)
class WorkflowRecord:
    uuid: str
    workflow_name: str
    workflow_description: str
    workflow: str
    create_date: str
    test_result: bool
    validate_date: str
    last_start_date: str = ""
    last_end_date: str = ""
    run_count: int = 0
    sucess_count: int = 0
    fail_count: int = 0
    last_success: bool = False
    owner: int = 0
    distribute: bool = False


def user_owns_workflow(record: WorkflowRecord, user_idx: int) -> bool:
    return int(record.owner or 0) == int(user_idx) and int(user_idx) > 0


def user_can_view_workflow(record: WorkflowRecord, user_idx: int) -> bool:
    if int(user_idx) <= 0:
        return False
    return user_owns_workflow(record, user_idx) or bool(record.distribute)


def _row_to_work_node(row) -> WorkNodeRecord:
    keys = row.keys() if hasattr(row, "keys") else []
    description = row["work_description"] if "work_description" in keys else ""
    script_type = row["script_type"] if "script_type" in keys else ""
    create_date = row["create_date"] if "create_date" in keys else ""
    validate_date = row["validate_date"] if "validate_date" in keys else ""
    last_start_date = row["last_start_date"] if "last_start_date" in keys else ""
    last_end_date = row["last_end_date"] if "last_end_date" in keys else ""
    last_success = row["last_success"] if "last_success" in keys else 0
    last_fail_reason = row["last_fail_reason"] if "last_fail_reason" in keys else ""
    use_previous_work_result = (
        row["use_previous_work_result"] if "use_previous_work_result" in keys else 0
    )
    work_report = row["work_report"] if "work_report" in keys else ""
    owner = row["owner"] if "owner" in keys else 0
    return WorkNodeRecord(
        uuid=str(row["uuid"] or ""),
        owner=int(owner or 0),
        work_name=str(row["work_name"] or ""),
        work_description=str(description or ""),
        target_agent=int(row["target_agent"] or 0),
        work_script=str(row["work_script"] or ""),
        script_type=normalize_script_type(str(script_type or "")),
        test_result=bool(int(row["test_result"] or 0)),
        files=str(row["files"] or ""),
        create_date=str(create_date or ""),
        validate_date=str(validate_date or ""),
        last_start_date=str(last_start_date or ""),
        last_end_date=str(last_end_date or ""),
        last_success=bool(int(last_success or 0)),
        last_fail_reason=str(last_fail_reason or "")[:200],
        use_previous_work_result=bool(int(use_previous_work_result or 0)),
        work_report=str(work_report or "")[:200],
    )


def _row_to_workflow(row) -> WorkflowRecord:
    keys = row.keys() if hasattr(row, "keys") else []
    owner = row["owner"] if "owner" in keys else 0
    distribute = row["distribute"] if "distribute" in keys else False
    create_date = row["create_date"] if "create_date" in keys else ""
    validate_date = row["validate_date"] if "validate_date" in keys else ""
    test_result = row["test_result"] if "test_result" in keys else 0
    last_start_date = row["last_start_date"] if "last_start_date" in keys else ""
    last_end_date = row["last_end_date"] if "last_end_date" in keys else ""
    run_count = row["run_count"] if "run_count" in keys else 0
    sucess_count = row["sucess_count"] if "sucess_count" in keys else 0
    fail_count = row["fail_count"] if "fail_count" in keys else 0
    last_success = row["last_success"] if "last_success" in keys else 0
    return WorkflowRecord(
        uuid=str(row["uuid"] or ""),
        owner=int(owner or 0),
        distribute=bool(distribute),
        workflow_name=str(row["workflow_name"] or ""),
        workflow_description=str(row["workflow_description"] or ""),
        workflow=str(row["workflow"] or ""),
        create_date=str(create_date or ""),
        test_result=bool(int(test_result or 0)),
        validate_date=str(validate_date or ""),
        last_start_date=str(last_start_date or ""),
        last_end_date=str(last_end_date or ""),
        run_count=int(run_count or 0),
        sucess_count=int(sucess_count or 0),
        fail_count=int(fail_count or 0),
        last_success=bool(int(last_success or 0)),
    )


def list_work_nodes(database_path: str | Path) -> list[WorkNodeRecord]:
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        rows = connection.execute(
            f"SELECT {_WORK_NODE_SELECT} FROM work_node ORDER BY create_date ASC, uuid ASC"
        ).fetchall()
    return [_row_to_work_node(row) for row in rows]


def list_work_nodes_visible(database_path: str | Path, user_idx: int) -> list[WorkNodeRecord]:
    """Owned nodes, or nodes referenced by workflows the user can view."""
    uid = int(user_idx or 0)
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        owned_rows = connection.execute(
            f"""
            SELECT {_WORK_NODE_SELECT}
            FROM work_node
            WHERE owner = ?
            ORDER BY create_date ASC, uuid ASC
            """,
            (uid,),
        ).fetchall()
        visible_workflows = connection.execute(
            f"""
            SELECT {_WORKFLOW_SELECT}
            FROM workflow
            WHERE owner = ? OR distribute = TRUE
            """,
            (uid,),
        ).fetchall()
    by_uuid = {row["uuid"]: _row_to_work_node(row) for row in owned_rows}
    referenced: set[str] = set()
    for wf_row in visible_workflows:
        record = _row_to_workflow(wf_row)
        referenced |= work_uuids_from_expression(record.workflow)
    missing = [key for key in referenced if key not in by_uuid]
    if missing:
        with get_connection(database_path) as connection:
            ensure_workflow_tables(connection)
            for node_uuid in missing:
                row = connection.execute(
                    f"SELECT {_WORK_NODE_SELECT} FROM work_node WHERE uuid = ?",
                    (node_uuid,),
                ).fetchone()
                if row is not None:
                    by_uuid[node_uuid] = _row_to_work_node(row)
    return sorted(by_uuid.values(), key=lambda item: (item.create_date, item.uuid))


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
    use_previous_work_result: bool = False,
    work_report: str = "",
    uuid: str | None = None,
    owner: int = 0,
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
                uuid, owner, work_name, work_description, target_agent, work_script,
                script_type, test_result, files, create_date, validate_date,
                last_start_date, last_end_date, last_success, last_fail_reason,
                use_previous_work_result, work_report
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', 0, '', ?, ?)
            RETURNING {_WORK_NODE_SELECT}
            """,
            (
                node_uuid,
                int(owner or 0),
                work_name.strip() or "새 작업노드",
                (work_description or "").strip()[:500],
                int(target_agent),
                work_script or "",
                normalized_script_type,
                1 if test_result else 0,
                (files or "").strip()[:300],
                created_at,
                validate_at,
                1 if use_previous_work_result else 0,
                (work_report or "").strip()[:200],
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
    use_previous_work_result: bool = False,
    work_report: str = "",
) -> WorkNodeRecord | None:
    existing = get_work_node_by_uuid(database_path, node_uuid)
    if existing is None:
        return None
    if test_result:
        validate_date = now_job_datetime()
    else:
        validate_date = ""
    normalized_script_type = normalize_script_type(script_type)
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        connection.execute(
            """
            UPDATE work_node
            SET work_name = ?, work_description = ?, target_agent = ?, work_script = ?,
                script_type = ?, test_result = ?, files = ?, validate_date = ?,
                use_previous_work_result = ?, work_report = ?
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
                1 if use_previous_work_result else 0,
                (work_report or "").strip()[:200],
                existing.uuid,
            ),
        )
    return get_work_node_by_uuid(database_path, existing.uuid)


def update_work_node_validation(
    database_path: str | Path,
    node_uuid: str,
    *,
    test_result: bool,
) -> WorkNodeRecord | None:
    """Update only validation flags."""
    existing = get_work_node_by_uuid(database_path, node_uuid)
    if existing is None:
        return None
    validate_date = now_job_datetime() if test_result else ""
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        connection.execute(
            """
            UPDATE work_node
            SET test_result = ?, validate_date = ?
            WHERE uuid = ?
            """,
            (1 if test_result else 0, validate_date, existing.uuid),
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


def list_workflows_visible(database_path: str | Path, user_idx: int) -> list[WorkflowRecord]:
    uid = int(user_idx or 0)
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        rows = connection.execute(
            f"""
            SELECT {_WORKFLOW_SELECT}
            FROM workflow
            WHERE owner = ? OR distribute = TRUE
            ORDER BY create_date DESC, uuid DESC
            """,
            (uid,),
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
    owner: int = 0,
    distribute: bool = False,
    uuid: str | None = None,
) -> WorkflowRecord:
    created_at = now_job_datetime()
    workflow_uuid = _normalize_uuid(uuid)
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        row = connection.execute(
            f"""
            INSERT INTO workflow (
                uuid, owner, distribute, workflow_name, workflow_description, workflow,
                create_date, test_result, validate_date,
                last_start_date, last_end_date, run_count, sucess_count, fail_count, last_success
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, '', '', '', 0, 0, 0, 0)
            RETURNING {_WORKFLOW_SELECT}
            """,
            (
                workflow_uuid,
                int(owner or 0),
                bool(distribute),
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
    distribute: bool | None = None,
) -> WorkflowRecord | None:
    existing = get_workflow_by_uuid(database_path, workflow_uuid)
    if existing is None:
        return None
    next_distribute = existing.distribute if distribute is None else bool(distribute)
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        connection.execute(
            """
            UPDATE workflow
            SET workflow_name = ?, workflow_description = ?, workflow = ?, distribute = ?
            WHERE uuid = ?
            """,
            (
                workflow_name.strip(),
                (workflow_description or "").strip()[:500],
                (workflow or "").strip(),
                next_distribute,
                existing.uuid,
            ),
        )
    return get_workflow_by_uuid(database_path, existing.uuid)


def set_workflow_distribute(
    database_path: str | Path,
    workflow_uuid: str,
    distribute: bool,
) -> WorkflowRecord | None:
    existing = get_workflow_by_uuid(database_path, workflow_uuid)
    if existing is None:
        return None
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        connection.execute(
            "UPDATE workflow SET distribute = ? WHERE uuid = ?",
            (bool(distribute), existing.uuid),
        )
    return get_workflow_by_uuid(database_path, existing.uuid)


def clone_workflow(
    database_path: str | Path,
    source_uuid: str,
    *,
    new_owner: int,
) -> WorkflowRecord:
    """Deep-copy a workflow and all referenced work_nodes for ``new_owner``."""
    source = get_workflow_by_uuid(database_path, source_uuid)
    if source is None:
        raise ValueError("작업 워크플로우를 찾을 수 없습니다.")
    owner_idx = int(new_owner or 0)
    if owner_idx <= 0:
        raise ValueError("복제 소유자가 올바르지 않습니다.")

    referenced = sorted(work_uuids_from_expression(source.workflow))
    uuid_map: dict[str, str] = {}
    for old_uuid in referenced:
        node = get_work_node_by_uuid(database_path, old_uuid)
        if node is None:
            continue
        new_uuid = _new_uuid()
        uuid_map[old_uuid] = new_uuid
        create_work_node(
            database_path,
            work_name=node.work_name,
            work_description=node.work_description,
            target_agent=node.target_agent,
            work_script=node.work_script,
            script_type=node.script_type,
            test_result=node.test_result,
            files=node.files,
            use_previous_work_result=node.use_previous_work_result,
            work_report=node.work_report,
            uuid=new_uuid,
            owner=owner_idx,
        )
        source_dir = work_node_upload_dir(old_uuid)
        if source_dir.is_dir():
            target_dir = work_node_upload_dir(new_uuid)
            shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)

    remapped = rewrite_expression_uuid_map(source.workflow, uuid_map)
    cloned_name = f"{source.workflow_name} (복제)".strip()
    if len(cloned_name) > 100:
        cloned_name = f"{source.workflow_name[:90]}…(복제)"
    return create_workflow(
        database_path,
        workflow_name=cloned_name,
        workflow_description=source.workflow_description,
        workflow=remapped,
        owner=owner_idx,
        distribute=False,
    )


def delete_workflow(database_path: str | Path, workflow_uuid: str) -> bool:
    key = (workflow_uuid or "").strip()
    if not key:
        return False
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        cursor = connection.execute("DELETE FROM workflow WHERE uuid = ?", (key,))
        return int(cursor.rowcount or 0) > 0


def mark_workflow_run_started(database_path: str | Path, workflow_uuid: str) -> WorkflowRecord | None:
    existing = get_workflow_by_uuid(database_path, workflow_uuid)
    if existing is None:
        return None
    started = now_job_datetime()
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        connection.execute(
            """
            UPDATE workflow
            SET last_start_date = ?, last_end_date = '', run_count = run_count + 1,
                last_success = 0
            WHERE uuid = ?
            """,
            (started, existing.uuid),
        )
    return get_workflow_by_uuid(database_path, existing.uuid)


def mark_workflow_run_finished(
    database_path: str | Path,
    workflow_uuid: str,
    *,
    success: bool,
) -> WorkflowRecord | None:
    existing = get_workflow_by_uuid(database_path, workflow_uuid)
    if existing is None:
        return None
    ended = now_job_datetime()
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        if success:
            connection.execute(
                """
                UPDATE workflow
                SET last_end_date = ?, last_success = 1, sucess_count = sucess_count + 1
                WHERE uuid = ?
                """,
                (ended, existing.uuid),
            )
        else:
            connection.execute(
                """
                UPDATE workflow
                SET last_end_date = ?, last_success = 0, fail_count = fail_count + 1
                WHERE uuid = ?
                """,
                (ended, existing.uuid),
            )
    return get_workflow_by_uuid(database_path, existing.uuid)


def mark_work_node_run_started(database_path: str | Path, node_uuid: str) -> WorkNodeRecord | None:
    existing = get_work_node_by_uuid(database_path, node_uuid)
    if existing is None:
        return None
    started = now_job_datetime()
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        connection.execute(
            """
            UPDATE work_node
            SET last_start_date = ?, last_end_date = '', last_success = 0, last_fail_reason = ''
            WHERE uuid = ?
            """,
            (started, existing.uuid),
        )
    return get_work_node_by_uuid(database_path, existing.uuid)


def mark_work_node_run_finished(
    database_path: str | Path,
    node_uuid: str,
    *,
    success: bool,
    fail_reason: str = "",
) -> WorkNodeRecord | None:
    existing = get_work_node_by_uuid(database_path, node_uuid)
    if existing is None:
        return None
    ended = now_job_datetime()
    reason = (fail_reason or "").strip()[:200] if not success else ""
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        connection.execute(
            """
            UPDATE work_node
            SET last_end_date = ?, last_success = ?, last_fail_reason = ?
            WHERE uuid = ?
            """,
            (ended, 1 if success else 0, reason, existing.uuid),
        )
    return get_work_node_by_uuid(database_path, existing.uuid)


_WORKFLOW_HISTORY_SELECT = """
    idx, uuid, start_date, end_date, finish_success, result_file, user_idx
"""


@dataclass(frozen=True)
class WorkflowHistoryRecord:
    idx: int
    uuid: str
    start_date: str
    end_date: str
    finish_success: bool
    result_file: str
    user_idx: int = 1


def _row_to_workflow_history(row) -> WorkflowHistoryRecord:
    keys = row.keys() if hasattr(row, "keys") else []
    user_idx = row["user_idx"] if "user_idx" in keys else 1
    return WorkflowHistoryRecord(
        idx=int(row["idx"]),
        uuid=str(row["uuid"] or ""),
        start_date=str(row["start_date"] or ""),
        end_date=str(row["end_date"] or ""),
        finish_success=bool(int(row["finish_success"] or 0)),
        result_file=str(row["result_file"] or "")[:1000],
        user_idx=int(user_idx or 1) or 1,
    )


def insert_workflow_history(
    database_path: str | Path,
    *,
    workflow_uuid: str,
    start_date: str,
    end_date: str,
    finish_success: bool,
    result_file: str,
    user_idx: int = 1,
) -> WorkflowHistoryRecord:
    key = (workflow_uuid or "").strip()
    if not key:
        raise ValueError("workflow uuid가 비어 있습니다.")
    executor_idx = int(user_idx or 0)
    if executor_idx <= 0:
        executor_idx = 1
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        row = connection.execute(
            f"""
            INSERT INTO workflow_history (
                uuid, start_date, end_date, finish_success, result_file, user_idx
            ) VALUES (?, ?, ?, ?, ?, ?)
            RETURNING {_WORKFLOW_HISTORY_SELECT}
            """,
            (
                key,
                (start_date or "").strip(),
                (end_date or "").strip(),
                1 if finish_success else 0,
                (result_file or "").strip()[:1000],
                executor_idx,
            ),
        ).fetchone()
    return _row_to_workflow_history(row)


def list_workflow_history(
    database_path: str | Path,
    workflow_uuid: str,
) -> list[WorkflowHistoryRecord]:
    key = (workflow_uuid or "").strip()
    if not key:
        return []
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        rows = connection.execute(
            f"""
            SELECT {_WORKFLOW_HISTORY_SELECT}
            FROM workflow_history
            WHERE uuid = ?
            ORDER BY idx DESC
            """,
            (key,),
        ).fetchall()
    return [_row_to_workflow_history(row) for row in rows]


def get_workflow_history_by_idx(
    database_path: str | Path,
    history_idx: int,
) -> WorkflowHistoryRecord | None:
    with get_connection(database_path) as connection:
        ensure_workflow_tables(connection)
        row = connection.execute(
            f"""
            SELECT {_WORKFLOW_HISTORY_SELECT}
            FROM workflow_history
            WHERE idx = ?
            """,
            (int(history_idx),),
        ).fetchone()
    return _row_to_workflow_history(row) if row is not None else None
