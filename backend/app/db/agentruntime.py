"""AXIT platform agent runtime connection records."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from backend.app.agents.base import AgentDefinition
from backend.app.db.database import get_connection
from backend.app.timezone import DISPLAY_TIMEZONE, now_display_datetime

AGENTRUNTIME_TYPE_MOCKUP = 0
AGENTRUNTIME_TYPE_EXTERNAL = 1

MOCKUP_CLIENT_ID = "mock-client-id"
MOCKUP_CLIENT_SECRET = "mock-client-secret"
DEFAULT_SERVICE_ID = "prvops"

_AXIT_AGENT_ID_NAMESPACE = uuid.UUID("00000000-0000-4000-8000-000000000000")

_AGENTRUNTIME_SELECT = """
    SELECT idx, type, agent_name, agent_id, local_agent_id,
           description, registered_date, service_id
    FROM agentruntime
"""


@dataclass(frozen=True)
class StoredAgentRuntime:
    idx: int
    type: int
    agent_name: str
    agent_id: str
    local_agent_id: str
    description: str
    registered_date: str
    service_id: str


def format_registered_datetime(dt: datetime | None = None) -> str:
    current = dt if dt is not None else now_display_datetime()
    if current.tzinfo is None:
        current = current.replace(tzinfo=DISPLAY_TIMEZONE)
    else:
        current = current.astimezone(DISPLAY_TIMEZONE)
    return current.isoformat(timespec="seconds")


def normalize_registered_datetime(value: str) -> str:
    text = value.strip()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return f"{text}T00:00:00+09:00"
    return text


def build_axit_agent_id(local_agent_id: str) -> str:
    """Stable UUID for AXIT invoke path, derived from local agent_id."""
    return str(uuid.uuid5(_AXIT_AGENT_ID_NAMESPACE, local_agent_id.strip()))


def runtime_mode_for_type(runtime_type: int) -> str:
    return "http" if runtime_type == AGENTRUNTIME_TYPE_EXTERNAL else "mock"


def build_agent_chat_url(record: StoredAgentRuntime) -> str:
    """AXIT agent chat endpoint: {AGENT_URL}/{agent_id}[/invoke for external]."""
    from backend.app.services.axit_config import resolve_axit_agent_url

    runtime_mode = runtime_mode_for_type(record.type)
    base = f"{resolve_axit_agent_url(runtime_mode=runtime_mode).rstrip('/')}/{record.agent_id}"
    if record.type == AGENTRUNTIME_TYPE_EXTERNAL:
        return f"{base}/invoke"
    return base


def _row_to_stored_agentruntime(row) -> StoredAgentRuntime:
    local_agent_id = str(row["local_agent_id"] or "").strip()
    return StoredAgentRuntime(
        idx=int(row["idx"]),
        type=int(row["type"]),
        agent_name=str(row["agent_name"]),
        agent_id=str(row["agent_id"]),
        local_agent_id=local_agent_id,
        description=str(row["description"]),
        registered_date=normalize_registered_datetime(str(row["registered_date"])),
        service_id=str(row["service_id"]),
    )


def resolve_active_agentruntime_type(runtime_mode: str | None = None) -> int:
    """Map AGENT_RUNTIME_MODE to agentruntime.type (0=mock, 1=http/external)."""
    from backend.app.config import resolve_agent_runtime_mode
    from backend.app.services.agent_runtime_client import normalize_runtime_mode

    mode = normalize_runtime_mode(runtime_mode or resolve_agent_runtime_mode())
    if mode == "http":
        return AGENTRUNTIME_TYPE_EXTERNAL
    return AGENTRUNTIME_TYPE_MOCKUP


def mockup_row_from_definition(
    definition: AgentDefinition,
    *,
    registered_at: datetime | None = None,
) -> dict[str, object]:
    from backend.app.services.axit_config import resolve_axit_service_id

    return {
        "type": AGENTRUNTIME_TYPE_MOCKUP,
        "agent_name": definition.name,
        "agent_id": build_axit_agent_id(definition.agent_id),
        "local_agent_id": definition.agent_id,
        "description": definition.role,
        "registered_date": format_registered_datetime(registered_at),
        "service_id": resolve_axit_service_id(),
    }


def list_agentruntime_records(
    database_path: str | Path,
    *,
    runtime_mode: str | None = None,
) -> list[StoredAgentRuntime]:
    active_type = resolve_active_agentruntime_type(runtime_mode)
    with get_connection(database_path) as connection:
        rows = connection.execute(
            f"""
            {_AGENTRUNTIME_SELECT}
            WHERE type = ?
            ORDER BY idx
            """,
            (active_type,),
        ).fetchall()
    return [_row_to_stored_agentruntime(row) for row in rows]


def get_agentruntime_by_idx(database_path: str | Path, idx: int) -> StoredAgentRuntime | None:
    with get_connection(database_path) as connection:
        row = connection.execute(
            f"""
            {_AGENTRUNTIME_SELECT}
            WHERE idx = ?
            """,
            (idx,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_stored_agentruntime(row)


def get_agentruntime_by_agent_id(
    database_path: str | Path,
    agent_id: str,
    *,
    runtime_mode: str | None = None,
) -> StoredAgentRuntime | None:
    active_type = resolve_active_agentruntime_type(runtime_mode)
    with get_connection(database_path) as connection:
        row = connection.execute(
            f"""
            {_AGENTRUNTIME_SELECT}
            WHERE agent_id = ? AND type = ?
            """,
            (agent_id.strip(), active_type),
        ).fetchone()
    if row is None:
        return None
    return _row_to_stored_agentruntime(row)


def get_agentruntime_by_local_agent_id(
    database_path: str | Path,
    local_agent_id: str,
    *,
    runtime_mode: str | None = None,
) -> StoredAgentRuntime | None:
    active_type = resolve_active_agentruntime_type(runtime_mode)
    normalized = local_agent_id.strip()
    with get_connection(database_path) as connection:
        row = connection.execute(
            f"""
            {_AGENTRUNTIME_SELECT}
            WHERE local_agent_id = ? AND type = ?
            """,
            (normalized, active_type),
        ).fetchone()
    if row is None:
        return None
    return _row_to_stored_agentruntime(row)


def resolve_local_agent_id(
    database_path: str | Path,
    axit_agent_id: str,
    *,
    runtime_mode: str | None = None,
) -> str | None:
    record = get_agentruntime_by_agent_id(
        database_path,
        axit_agent_id,
        runtime_mode=runtime_mode,
    )
    if record is None:
        return None
    local_agent_id = record.local_agent_id.strip()
    return local_agent_id or None


def insert_agentruntime_records(
    connection,
    rows: list[dict[str, object]],
) -> int:
    if not rows:
        return 0
    connection.executemany(
        """
        INSERT INTO agentruntime (
            type, agent_name, agent_id, local_agent_id, description,
            registered_date, service_id
        )
        VALUES (
            :type, :agent_name, :agent_id, :local_agent_id, :description,
            :registered_date, :service_id
        )
        """,
        rows,
    )
    return len(rows)


def create_agentruntime_record(
    database_path: str | Path,
    *,
    runtime_type: int,
    agent_name: str,
    agent_id: str,
    local_agent_id: str,
    description: str,
    service_id: str,
    registered_date: str | None = None,
) -> StoredAgentRuntime:
    registered = normalize_registered_datetime(
        registered_date or format_registered_datetime(),
    )
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO agentruntime (
                type, agent_name, agent_id, local_agent_id, description,
                registered_date, service_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                runtime_type,
                agent_name.strip(),
                agent_id.strip(),
                local_agent_id.strip(),
                description.strip(),
                registered,
                service_id.strip(),
            ),
        )
        connection.commit()
        created_idx = int(cursor.lastrowid)
    record = get_agentruntime_by_idx(database_path, created_idx)
    if record is None:
        raise RuntimeError("Failed to load created agentruntime record")
    return record


def update_agentruntime_record(
    database_path: str | Path,
    idx: int,
    *,
    agent_name: str,
    agent_id: str,
    local_agent_id: str,
    description: str,
    service_id: str,
    registered_date: str,
) -> StoredAgentRuntime | None:
    existing = get_agentruntime_by_idx(database_path, idx)
    if existing is None:
        return None
    with get_connection(database_path) as connection:
        connection.execute(
            """
            UPDATE agentruntime
            SET agent_name = ?, agent_id = ?, local_agent_id = ?,
                description = ?, registered_date = ?, service_id = ?
            WHERE idx = ?
            """,
            (
                agent_name.strip(),
                agent_id.strip(),
                local_agent_id.strip(),
                description.strip(),
                normalize_registered_datetime(registered_date),
                service_id.strip(),
                idx,
            ),
        )
        connection.commit()
    return get_agentruntime_by_idx(database_path, idx)


def delete_agentruntime_record(database_path: str | Path, idx: int) -> bool:
    with get_connection(database_path) as connection:
        cursor = connection.execute("DELETE FROM agentruntime WHERE idx = ?", (idx,))
        connection.commit()
        return cursor.rowcount > 0
