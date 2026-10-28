"""AXIT platform agent runtime connection records."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from backend.app.agents.base import AgentDefinition
from backend.app.db.database import get_connection
from backend.app.db.prod_mode import PROD_MODE_DEV, PROD_MODE_PROD, normalize_prod_mode
from backend.app.timezone import DISPLAY_TIMEZONE, now_display_datetime

AGENTRUNTIME_TYPE_MOCKUP = 0
AGENTRUNTIME_TYPE_EXTERNAL = 1

MOCKUP_CLIENT_ID = "mock-client-id"
MOCKUP_CLIENT_SECRET = "mock-client-secret"
DEFAULT_SERVICE_ID = "prvops"

NON_TALKABLE_LOCAL_AGENT_IDS: frozenset[str] = frozenset({"job_auditor", "WORKFLOW_AGENT"})

ORCHESTRATOR_LOCAL_AGENT_IDS: frozenset[str] = frozenset({
    "archi-analysis",
    "job_auditor",
})

_AXIT_AGENT_ID_NAMESPACE = uuid.UUID("00000000-0000-4000-8000-000000000000")


@dataclass(frozen=True)
class MockAgentRuntimePreset:
    agent_name: str
    local_agent_id: str
    description: str


_AGENTRUNTIME_SELECT = """
    SELECT idx, type, agent_name, agent_id, local_agent_id,
           description, registered_date, service_id, talkable, is_orchestrator, is_prod
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
    is_prod: int = PROD_MODE_DEV


def ensure_agentruntime_is_prod_column(connection) -> None:
    """Add is_prod and replace unique(type, agent_id) with unique(type, agent_id, is_prod)."""
    connection.execute(
        """
        ALTER TABLE agentruntime
        ADD COLUMN IF NOT EXISTS is_prod INTEGER NOT NULL DEFAULT 1
        """
    )
    connection.execute(
        "ALTER TABLE agentruntime DROP CONSTRAINT IF EXISTS agentruntime_type_agent_id_key"
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_agentruntime_type_agent_id_is_prod
        ON agentruntime (type, agent_id, is_prod)
        """
    )


def default_talkable_for_local_agent_id(local_agent_id: str) -> bool:
    return local_agent_id.strip() not in NON_TALKABLE_LOCAL_AGENT_IDS


def default_is_orchestrator_for_local_agent_id(local_agent_id: str) -> bool:
    return local_agent_id.strip() in ORCHESTRATOR_LOCAL_AGENT_IDS


def build_talkable_by_catalog_agent_id(
    database_path: str | Path,
    *,
    runtime_mode: str | None = None,
    is_prod: int | None = None,
) -> dict[str, bool]:
    return {
        catalog_agent_id(record): record.talkable
        for record in list_agentruntime_records(
            database_path,
            runtime_mode=runtime_mode,
            is_prod=is_prod,
        )
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
    is_prod: int | None = None,
) -> StoredAgentRuntime | None:
    """Resolve agentruntime for AXIT invoke using catalog id or explicit idx.

    When ``is_prod`` is set, an explicit idx that belongs to the other platform is
    rematched by catalog id for the requested mode (or rejected if none exists).
    """
    from backend.app.config import resolve_agent_runtime_mode
    from backend.app.db.prod_mode import agentruntime_visible_for_mode
    from backend.app.services.agent_runtime_client import normalize_runtime_mode

    mode = normalize_runtime_mode(runtime_mode or resolve_agent_runtime_mode())
    requested_catalog_id = catalog_agent_id.strip()

    if agentruntime_idx is not None:
        record = get_agentruntime_by_idx(database_path, agentruntime_idx)
        if record is not None:
            if is_prod is None or agentruntime_visible_for_mode(
                is_prod=record.is_prod,
                current_prod_mode=is_prod,
            ):
                return record
            rematch_keys = [
                record.local_agent_id.strip() or record.agent_id.strip(),
                record.local_agent_id.strip(),
                record.agent_id.strip(),
                requested_catalog_id,
            ]
            seen: set[str] = set()
            for key in rematch_keys:
                normalized = key.strip()
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                rematched = get_agentruntime_by_local_agent_id(
                    database_path,
                    normalized,
                    runtime_mode=mode,
                    is_prod=is_prod,
                )
                if rematched is not None:
                    return rematched
                rematched = get_agentruntime_by_agent_id(
                    database_path,
                    normalized,
                    runtime_mode=mode,
                    is_prod=is_prod,
                )
                if rematched is not None:
                    return rematched
            return None

    if not requested_catalog_id:
        return None

    record = get_agentruntime_by_local_agent_id(
        database_path,
        requested_catalog_id,
        runtime_mode=mode,
        is_prod=is_prod,
    )
    if record is not None:
        return record

    return get_agentruntime_by_agent_id(
        database_path,
        requested_catalog_id,
        runtime_mode=mode,
        is_prod=is_prod,
    )


def agent_registered_for_prod_mode(
    database_path: str | Path,
    agent_id: str,
    *,
    runtime_mode: str | None = None,
    is_prod: int,
) -> bool:
    """True when ``agent_id`` has an agentruntime row for the given platform mode."""
    return (
        resolve_agentruntime_for_invoke(
            database_path,
            catalog_agent_id=agent_id,
            runtime_mode=runtime_mode,
            is_prod=is_prod,
        )
        is not None
    )


def _row_is_prod(row) -> int:
    try:
        return normalize_prod_mode(row["is_prod"])
    except (KeyError, IndexError, TypeError, ValueError):
        return PROD_MODE_DEV


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
        is_prod=_row_is_prod(row),
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
        "is_prod": PROD_MODE_DEV,
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
        "is_prod": PROD_MODE_DEV,
    }


def list_agentruntime_records(
    database_path: str | Path,
    *,
    runtime_mode: str | None = None,
    is_prod: int | None = None,
) -> list[StoredAgentRuntime]:
    active_type = resolve_active_agentruntime_type(runtime_mode)
    with get_connection(database_path) as connection:
        ensure_agentruntime_is_prod_column(connection)
        if is_prod is None:
            rows = connection.execute(
                f"""
                {_AGENTRUNTIME_SELECT}
                WHERE type = ?
                ORDER BY idx
                """,
                (active_type,),
            ).fetchall()
        else:
            rows = connection.execute(
                f"""
                {_AGENTRUNTIME_SELECT}
                WHERE type = ? AND is_prod = ?
                ORDER BY idx
                """,
                (active_type, normalize_prod_mode(is_prod)),
            ).fetchall()
    return [_row_to_stored_agentruntime(row) for row in rows]


def get_agentruntime_by_idx(database_path: str | Path, idx: int) -> StoredAgentRuntime | None:
    with get_connection(database_path) as connection:
        ensure_agentruntime_is_prod_column(connection)
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


def _get_agentruntime_by_column(
    database_path: str | Path,
    *,
    column: str,
    value: str,
    runtime_mode: str | None,
    is_prod: int | None,
) -> StoredAgentRuntime | None:
    """Single-row lookup; when is_prod is None and several rows match, prefer DEV (1)."""
    if column not in {"agent_id", "local_agent_id"}:
        raise ValueError(f"unsupported agentruntime lookup column: {column}")
    active_type = resolve_active_agentruntime_type(runtime_mode)
    with get_connection(database_path) as connection:
        ensure_agentruntime_is_prod_column(connection)
        if is_prod is None:
            row = connection.execute(
                f"""
                {_AGENTRUNTIME_SELECT}
                WHERE {column} = ? AND type = ?
                ORDER BY is_prod, idx
                LIMIT 1
                """,
                (value, active_type),
            ).fetchone()
        else:
            row = connection.execute(
                f"""
                {_AGENTRUNTIME_SELECT}
                WHERE {column} = ? AND type = ? AND is_prod = ?
                ORDER BY idx
                LIMIT 1
                """,
                (value, active_type, normalize_prod_mode(is_prod)),
            ).fetchone()
    if row is None:
        return None
    return _row_to_stored_agentruntime(row)


def get_agentruntime_by_agent_id(
    database_path: str | Path,
    agent_id: str,
    *,
    runtime_mode: str | None = None,
    is_prod: int | None = None,
) -> StoredAgentRuntime | None:
    return _get_agentruntime_by_column(
        database_path,
        column="agent_id",
        value=agent_id.strip(),
        runtime_mode=runtime_mode,
        is_prod=is_prod,
    )


def get_agentruntime_by_local_agent_id(
    database_path: str | Path,
    local_agent_id: str,
    *,
    runtime_mode: str | None = None,
    is_prod: int | None = None,
) -> StoredAgentRuntime | None:
    return _get_agentruntime_by_column(
        database_path,
        column="local_agent_id",
        value=local_agent_id.strip(),
        runtime_mode=runtime_mode,
        is_prod=is_prod,
    )


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
    ensure_agentruntime_is_prod_column(connection)
    rows_with_prod = [{**row, "is_prod": row.get("is_prod", PROD_MODE_DEV)} for row in rows]
    connection.executemany(
        """
        INSERT INTO agentruntime (
            type, agent_name, agent_id, local_agent_id, description,
            registered_date, service_id, talkable, is_orchestrator, is_prod
        )
        VALUES (
            :type, :agent_name, :agent_id, :local_agent_id, :description,
            :registered_date, :service_id, :talkable, :is_orchestrator, :is_prod
        )
        """,
        rows_with_prod,
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
    is_prod: int = PROD_MODE_DEV,
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
        ensure_agentruntime_is_prod_column(connection)
        cursor = connection.execute(
            """
            INSERT INTO agentruntime (
                type, agent_name, agent_id, local_agent_id, description,
                registered_date, service_id, talkable, is_orchestrator, is_prod
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                normalize_prod_mode(is_prod),
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
    talkable: bool,
    is_orchestrator: bool,
    is_prod: int | None = None,
) -> StoredAgentRuntime | None:
    existing = get_agentruntime_by_idx(database_path, idx)
    if existing is None:
        return None
    next_is_prod = existing.is_prod if is_prod is None else normalize_prod_mode(is_prod)
    with get_connection(database_path) as connection:
        ensure_agentruntime_is_prod_column(connection)
        connection.execute(
            """
            UPDATE agentruntime
            SET agent_name = ?, agent_id = ?, local_agent_id = ?,
                description = ?, registered_date = ?, service_id = ?,
                talkable = ?, is_orchestrator = ?, is_prod = ?
            WHERE idx = ?
            """,
            (
                agent_name.strip(),
                agent_id.strip(),
                local_agent_id.strip(),
                description.strip(),
                normalize_registered_datetime(registered_date),
                service_id.strip(),
                1 if talkable else 0,
                1 if is_orchestrator else 0,
                next_is_prod,
                idx,
            ),
        )
        connection.commit()
    return get_agentruntime_by_idx(database_path, idx)


def delete_agentruntime_record(database_path: str | Path, idx: int) -> bool:
    with get_connection(database_path) as connection:
        ensure_agentruntime_is_prod_column(connection)
        cursor = connection.execute("DELETE FROM agentruntime WHERE idx = ?", (idx,))
        connection.commit()
        return cursor.rowcount > 0


def ensure_mock_ansible_lint_agentruntime(database_path: str | Path) -> StoredAgentRuntime | None:
    """Insert mock-only ansible-lint agentruntime row if missing (not part of DB seed)."""
    from backend.app.agents.ansible_lint_agent import (
        ANSIBLE_LINT_AGENT,
        ANSIBLE_LINT_LOCAL_AGENT_ID,
    )

    existing = get_agentruntime_by_local_agent_id(
        database_path,
        ANSIBLE_LINT_LOCAL_AGENT_ID,
        runtime_mode="mock",
    )
    if existing is not None:
        return existing

    return create_agentruntime_record(
        database_path,
        runtime_type=AGENTRUNTIME_TYPE_MOCKUP,
        agent_name=ANSIBLE_LINT_AGENT.name,
        agent_id=build_axit_agent_id(ANSIBLE_LINT_LOCAL_AGENT_ID),
        local_agent_id=ANSIBLE_LINT_LOCAL_AGENT_ID,
        description=ANSIBLE_LINT_AGENT.role,
        service_id=DEFAULT_SERVICE_ID,
        talkable=True,
        is_orchestrator=False,
    )


def ensure_mock_workflow_agent_agentruntime(database_path: str | Path) -> StoredAgentRuntime | None:
    """Insert mock-only WORKFLOW_AGENT agentruntime row if missing (is_orchestrator=0)."""
    from backend.app.agents.mock_platform_agents import (
        WORKFLOW_AGENT_LOCAL_AGENT_ID,
        get_mock_platform_agent_spec,
    )

    existing = get_agentruntime_by_local_agent_id(
        database_path,
        WORKFLOW_AGENT_LOCAL_AGENT_ID,
        runtime_mode="mock",
    )
    if existing is not None:
        if existing.is_orchestrator:
            return update_agentruntime_record(
                database_path,
                existing.idx,
                agent_name=existing.agent_name,
                agent_id=existing.agent_id,
                local_agent_id=existing.local_agent_id,
                description=existing.description,
                service_id=existing.service_id,
                registered_date=existing.registered_date,
                talkable=existing.talkable,
                is_orchestrator=False,
            )
        return existing

    spec = get_mock_platform_agent_spec(WORKFLOW_AGENT_LOCAL_AGENT_ID)
    if spec is None:
        return None

    return create_agentruntime_record(
        database_path,
        runtime_type=AGENTRUNTIME_TYPE_MOCKUP,
        agent_name=spec.agent_name,
        agent_id=build_axit_agent_id(WORKFLOW_AGENT_LOCAL_AGENT_ID),
        local_agent_id=WORKFLOW_AGENT_LOCAL_AGENT_ID,
        description=spec.description,
        service_id=DEFAULT_SERVICE_ID,
        talkable=default_talkable_for_local_agent_id(WORKFLOW_AGENT_LOCAL_AGENT_ID),
        is_orchestrator=False,
    )


def ensure_mock_infra_search_agentruntime(database_path: str | Path) -> StoredAgentRuntime | None:
    """Insert mock-only INFRA_SEARCH_AGENT agentruntime row if missing (standalone invoke service)."""
    from backend.app.infra_search_agent.settings import AGENT_ID, AGENT_NAME

    existing = get_agentruntime_by_local_agent_id(
        database_path,
        AGENT_ID,
        runtime_mode="mock",
    )
    if existing is not None:
        return existing

    description = (
        "Inventory search via inventory MCP "
        "(getInventoryList, getInventorySchema, readDataUsingSQL)."
    )
    return create_agentruntime_record(
        database_path,
        runtime_type=AGENTRUNTIME_TYPE_MOCKUP,
        agent_name=AGENT_NAME,
        agent_id=build_axit_agent_id(AGENT_ID),
        local_agent_id=AGENT_ID,
        description=description,
        service_id=DEFAULT_SERVICE_ID,
        talkable=default_talkable_for_local_agent_id(AGENT_ID),
        is_orchestrator=default_is_orchestrator_for_local_agent_id(AGENT_ID),
    )


def ensure_mock_private_cloud_agentruntime(database_path: str | Path) -> StoredAgentRuntime | None:
    """Insert mock-only PRIVATE_CLOUD_AGENT agentruntime row if missing."""
    from backend.app.agents.private_cloud_agent import (
        PRIVATE_CLOUD_AGENT,
        PRIVATE_CLOUD_AGENT_ID,
    )

    existing = get_agentruntime_by_local_agent_id(
        database_path,
        PRIVATE_CLOUD_AGENT_ID,
        runtime_mode="mock",
    )
    if existing is not None:
        return existing

    return create_agentruntime_record(
        database_path,
        runtime_type=AGENTRUNTIME_TYPE_MOCKUP,
        agent_name=PRIVATE_CLOUD_AGENT.name,
        agent_id=build_axit_agent_id(PRIVATE_CLOUD_AGENT_ID),
        local_agent_id=PRIVATE_CLOUD_AGENT_ID,
        description=PRIVATE_CLOUD_AGENT.role,
        service_id=DEFAULT_SERVICE_ID,
        talkable=True,
        is_orchestrator=False,
    )


def ensure_mock_prod_agentruntime_duplicates(database_path: str | Path) -> int:
    """Insert PROD (is_prod=2) copies of mock DEV rows when missing. Returns inserted count."""
    inserted = 0
    for record in list_agentruntime_records(
        database_path,
        runtime_mode="mock",
        is_prod=PROD_MODE_DEV,
    ):
        if record.type != AGENTRUNTIME_TYPE_MOCKUP:
            continue
        with get_connection(database_path) as connection:
            ensure_agentruntime_is_prod_column(connection)
            existing = connection.execute(
                """
                SELECT idx FROM agentruntime
                WHERE type = ? AND agent_id = ? AND is_prod = ?
                """,
                (AGENTRUNTIME_TYPE_MOCKUP, record.agent_id, PROD_MODE_PROD),
            ).fetchone()
        if existing is not None:
            continue
        create_agentruntime_record(
            database_path,
            runtime_type=AGENTRUNTIME_TYPE_MOCKUP,
            agent_name=record.agent_name,
            agent_id=record.agent_id,
            local_agent_id=record.local_agent_id,
            description=record.description,
            service_id=record.service_id,
            registered_date=record.registered_date,
            talkable=record.talkable,
            is_orchestrator=record.is_orchestrator,
            is_prod=PROD_MODE_PROD,
        )
        inserted += 1
    return inserted
