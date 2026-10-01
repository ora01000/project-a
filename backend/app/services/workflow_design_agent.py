"""Resolve workflow design agent (WORKFLOW_AGENT) for mock/http runtimes."""

from __future__ import annotations

from pathlib import Path

from backend.app.agents.mock_platform_agents import WORKFLOW_AGENT_LOCAL_AGENT_ID
from backend.app.config import WorkflowAgentSettings, load_workflow_agent_settings
from backend.app.db.agentruntime import (
    StoredAgentRuntime,
    catalog_agent_id,
    get_agentruntime_by_agent_id,
    get_agentruntime_by_local_agent_id,
)
from backend.app.services.agent_runtime_client import normalize_runtime_mode


def _is_non_orchestrator(record: StoredAgentRuntime | None) -> bool:
    return record is not None and not record.is_orchestrator


def _find_http_workflow_agent_record(
    database_path: str | Path,
    *,
    settings: WorkflowAgentSettings,
) -> StoredAgentRuntime | None:
    if settings.axit_agent_id:
        record = get_agentruntime_by_agent_id(
            database_path,
            settings.axit_agent_id,
            runtime_mode="http",
        )
        if _is_non_orchestrator(record):
            return record

    local_candidates: list[str] = []
    for candidate in (
        settings.local_agent_id,
        WORKFLOW_AGENT_LOCAL_AGENT_ID,
    ):
        normalized = candidate.strip()
        if normalized and normalized not in local_candidates:
            local_candidates.append(normalized)

    for local_agent_id in local_candidates:
        record = get_agentruntime_by_local_agent_id(
            database_path,
            local_agent_id,
            runtime_mode="http",
        )
        if _is_non_orchestrator(record):
            return record

    return None


def try_resolve_workflow_agent_runtime_record(
    database_path: str | Path,
    runtime_mode: str,
    *,
    settings: WorkflowAgentSettings | None = None,
) -> StoredAgentRuntime | None:
    """Return workflow design agentruntime (is_orchestrator=0)."""
    agent_settings = settings or load_workflow_agent_settings()
    if normalize_runtime_mode(runtime_mode) == "mock":
        record = get_agentruntime_by_local_agent_id(
            database_path,
            agent_settings.local_agent_id or WORKFLOW_AGENT_LOCAL_AGENT_ID,
            runtime_mode="mock",
        )
        if _is_non_orchestrator(record):
            return record
        # Fallback to canonical mock id when settings point elsewhere.
        if (agent_settings.local_agent_id or "").strip() != WORKFLOW_AGENT_LOCAL_AGENT_ID:
            record = get_agentruntime_by_local_agent_id(
                database_path,
                WORKFLOW_AGENT_LOCAL_AGENT_ID,
                runtime_mode="mock",
            )
            if _is_non_orchestrator(record):
                return record
        return None

    return _find_http_workflow_agent_record(database_path, settings=agent_settings)


def try_resolve_workflow_agent_id(
    database_path: str | Path,
    runtime_mode: str,
    *,
    settings: WorkflowAgentSettings | None = None,
) -> str | None:
    """Return catalog agent id for workflow design chat, or None if unresolved."""
    agent_settings = settings or load_workflow_agent_settings()
    if normalize_runtime_mode(runtime_mode) == "mock":
        record = try_resolve_workflow_agent_runtime_record(
            database_path,
            runtime_mode,
            settings=agent_settings,
        )
        if record is not None:
            return catalog_agent_id(record)
        return (
            agent_settings.local_agent_id.strip()
            or WORKFLOW_AGENT_LOCAL_AGENT_ID
        )

    record = try_resolve_workflow_agent_runtime_record(
        database_path,
        runtime_mode,
        settings=agent_settings,
    )
    if record is None:
        return None
    return catalog_agent_id(record)


def resolve_workflow_agent_id(
    database_path: str | Path,
    runtime_mode: str,
    *,
    settings: WorkflowAgentSettings | None = None,
) -> str:
    agent_settings = settings or load_workflow_agent_settings()
    agent_id = try_resolve_workflow_agent_id(
        database_path,
        runtime_mode,
        settings=agent_settings,
    )
    if agent_id is not None:
        return agent_id

    raise RuntimeError(
        "agentruntime record not found for workflow design agent "
        f"(local_agent_id candidates: {agent_settings.local_agent_id!r}, "
        f"{WORKFLOW_AGENT_LOCAL_AGENT_ID!r}"
        + (
            f"; axit_agent_id={agent_settings.axit_agent_id!r}"
            if agent_settings.axit_agent_id
            else ""
        )
        + "). Register a non-orchestrator agent (is_orchestrator=0) in agentruntime or set "
        "WORKFLOW_AGENT_LOCAL_AGENT_ID / WORKFLOW_AGENT_AXIT_AGENT_ID."
    )


def is_workflow_design_agent_id(
    agent_id: str,
    database_path: str | Path,
    runtime_mode: str,
    *,
    settings: WorkflowAgentSettings | None = None,
) -> bool:
    """True when ``agent_id`` is the configured workflow design agent."""
    normalized = agent_id.strip()
    if not normalized:
        return False
    if normalized == WORKFLOW_AGENT_LOCAL_AGENT_ID:
        return True
    resolved = try_resolve_workflow_agent_id(
        database_path,
        runtime_mode,
        settings=settings,
    )
    return resolved is not None and resolved == normalized
