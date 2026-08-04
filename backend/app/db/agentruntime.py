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

NON_TALKABLE_LOCAL_AGENT_IDS: frozenset[str] = frozenset({"whatap-event", "job-scheduler"})

ORCHESTRATOR_LOCAL_AGENT_IDS: frozenset[str] = frozenset({
    "helpdesk",
    "whatap-event",
    "job-scheduler",
    "archi-analysis",
})

_AXIT_AGENT_ID_NAMESPACE = uuid.UUID("00000000-0000-4000-8000-000000000000")


@dataclass(frozen=True)
class MockAgentRuntimePreset:
    agent_name: str
    local_agent_id: str
    description: str


_AGENTRUNTIME_SELECT = """
    SELECT idx, type, agent_name, agent_id, local_agent_id,
           description, registered_date, service_id, talkable, is_orchestrator
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
    talkable: bool
    is_orchestrator: bool


def default_talkable_for_local_agent_id(local_agent_id: str) -> bool:
    return local_agent_id.strip() not in NON_TALKABLE_LOCAL_AGENT_IDS


def default_is_orchestrator_for_local_agent_id(local_agent_id: str) -> bool:
    return local_agent_id.strip() in ORCHESTRATOR_LOCAL_AGENT_IDS


def build_talkable_by_catalog_agent_id(
    database_path: str | Path,
    *,
    runtime_mode: str | None = None,
) -> dict[str, bool]:
    return {
        catalog_agent_id(record): record.talkable
        for record in list_agentruntime_records(database_path, runtime_mode=runtime_mode)
    }


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


def catalog_agent_id(record: StoredAgentRuntime) -> str:
    """Dashboard/assignment agent key: local_agent_id if set, otherwise AXIT agent_id."""
    local_agent_id = record.local_agent_id.strip()
    if local_agent_id:
        return local_agent_id
    return record.agent_id.strip()


def runtime_mode_for_type(runtime_type: int) -> str:
    return "http" if runtime_type == AGENTRUNTIME_TYPE_EXTERNAL else "mock"


def axit_runtime_api_family(record: StoredAgentRuntime) -> str:
    """Return API family name aligned with server-samples agentApi / orchestratorApi."""
    return "orchestrator" if record.is_orchestrator else "agent"


def _axit_runtime_resource_base(record: StoredAgentRuntime) -> str:
    """Base URL for one AXIT runtime resource: .../agents/v1/{id} or .../orchestrators/v1/{id}."""
    from backend.app.services.axit_config import resolve_axit_agent_url, resolve_axit_orchestrator_url

    runtime_mode = runtime_mode_for_type(record.type)
    if record.is_orchestrator:
        root = resolve_axit_orchestrator_url(runtime_mode=runtime_mode).rstrip("/")
    else:
        root = resolve_axit_agent_url(runtime_mode=runtime_mode).rstrip("/")
    return f"{root}/{record.agent_id}"


def build_axit_invoke_url(record: StoredAgentRuntime) -> str:
    """Invoke URL: agentApi.invokeAgent or orchestratorApi.invokeOrchestrator."""
    base = _axit_runtime_resource_base(record)
    if record.is_orchestrator:
        return f"{base}/invoke"
    if record.type == AGENTRUNTIME_TYPE_EXTERNAL:
        return f"{base}/invoke"
    return base


def build_axit_invocations_url(record: StoredAgentRuntime) -> str:
    """Invocations base URL for 504 polling after invoke."""
    return f"{_axit_runtime_resource_base(record)}/invocations"


def build_agent_chat_url(record: StoredAgentRuntime) -> str:
    """Backward-compatible alias for build_axit_invoke_url."""
    return build_axit_invoke_url(record)


def build_agent_invocations_url(record: StoredAgentRuntime) -> str:
    """Backward-compatible alias for build_axit_invocations_url."""
    return build_axit_invocations_url(record)


def resolve_agentruntime_for_invoke(
    database_path: str | Path,
    *,
    catalog_agent_id: str,
    agentruntime_idx: int | None = None,
    runtime_mode: str | None = None,
) -> StoredAgentRuntime | None:
    """Resolve agentruntime for AXIT invoke using catalog id or explicit idx."""
    from backend.app.config import resolve_agent_runtime_mode
    from backend.app.services.agent_runtime_client import normalize_runtime_mode

    mode = normalize_runtime_mode(runtime_mode or resolve_agent_runtime_mode())

    if agentruntime_idx is not None:
        record = get_agentruntime_by_idx(database_path, agentruntime_idx)
        if record is not None:
            return record

    normalized_catalog_id = catalog_agent_id.strip()
    if not normalized_catalog_id:
        return None

    record = get_agentruntime_by_local_agent_id(
        database_path,
        normalized_catalog_id,
        runtime_mode=mode,
    )
    if record is not None:
        return record

    return get_agentruntime_by_agent_id(
        database_path,
        normalized_catalog_id,
        runtime_mode=mode,
    )


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
        talkable=bool(row["talkable"]),
        is_orchestrator=bool(row["is_orchestrator"]),
    )


def resolve_active_agentruntime_type(runtime_mode: str | None = None) -> int:
    """Map AGENT_RUNTIME_MODE to agentruntime.type (0=mock, 1=http/external)."""
    from backend.app.config import resolve_agent_runtime_mode
    from backend.app.services.agent_runtime_client import normalize_runtime_mode

    mode = normalize_runtime_mode(runtime_mode or resolve_agent_runtime_mode())
    if mode == "http":
        return AGENTRUNTIME_TYPE_EXTERNAL
    return AGENTRUNTIME_TYPE_MOCKUP


def mockup_row_from_preset(
    preset: MockAgentRuntimePreset,
    *,
    registered_at: datetime | None = None,
) -> dict[str, object]:
    from backend.app.services.axit_config import resolve_axit_service_id

    local_agent_id = preset.local_agent_id.strip()
    return {
        "type": AGENTRUNTIME_TYPE_MOCKUP,
        "agent_name": preset.agent_name,
        "agent_id": build_axit_agent_id(local_agent_id),
        "local_agent_id": local_agent_id,
        "description": preset.description,
        "registered_date": format_registered_datetime(registered_at),
        "service_id": resolve_axit_service_id(),
        "talkable": default_talkable_for_local_agent_id(local_agent_id),
        "is_orchestrator": default_is_orchestrator_for_local_agent_id(local_agent_id),
    }


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
        "talkable": default_talkable_for_local_agent_id(definition.agent_id),
        "is_orchestrator": default_is_orchestrator_for_local_agent_id(definition.agent_id),
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
            registered_date, service_id, talkable, is_orchestrator
        )
        VALUES (
            :type, :agent_name, :agent_id, :local_agent_id, :description,
            :registered_date, :service_id, :talkable, :is_orchestrator
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
    talkable: bool | None = None,
    is_orchestrator: bool | None = None,
) -> StoredAgentRuntime:
    registered = normalize_registered_datetime(
        registered_date or format_registered_datetime(),
    )
    resolved_talkable = (
        default_talkable_for_local_agent_id(local_agent_id)
        if talkable is None
        else talkable
    )
    resolved_is_orchestrator = (
        default_is_orchestrator_for_local_agent_id(local_agent_id)
        if is_orchestrator is None
        else is_orchestrator
    )
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO agentruntime (
                type, agent_name, agent_id, local_agent_id, description,
                registered_date, service_id, talkable, is_orchestrator
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                runtime_type,
                agent_name.strip(),
                agent_id.strip(),
                local_agent_id.strip(),
                description.strip(),
                registered,
                service_id.strip(),
                1 if resolved_talkable else 0,
                1 if resolved_is_orchestrator else 0,
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
