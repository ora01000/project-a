from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from backend.app.agents.base import AgentDefinition
from backend.app.db.agentruntime import (
    build_talkable_by_catalog_agent_id,
    default_talkable_for_local_agent_id,
)
from backend.app.services.agent_runtime_client import (
    MOCK_RUNTIME_UNAVAILABLE_DETAIL,
    get_runtime_capabilities,
    normalize_runtime_mode,
)

router = APIRouter(tags=["agents"])


def _runtime_mode(request: Request) -> str:
    return normalize_runtime_mode(getattr(request.app.state, "agent_runtime_mode", "mock"))


def _sync_http_catalog_if_needed(request: Request) -> None:
    if _runtime_mode(request) != "http":
        return
    manager = request.app.state.agent_manager
    database_path = getattr(request.app.state, "database_path", None)
    if database_path is None:
        return
    manager.sync_remote_catalog(Path(database_path))


def _mock_runtime_summary(request: Request) -> dict:
    manager = request.app.state.agent_manager
    agent_status: dict[str, str] = manager.get_agent_health_status()
    mcp_status: dict[str, str] = {}
    if manager.mcp_manager is not None:
        mcp_status = dict(manager.mcp_manager.connection_status)
    return {"mcp": mcp_status, "agent_status": agent_status}


async def _runtime_summary(request: Request) -> dict:
    if not get_runtime_capabilities(_runtime_mode(request)).health_summary:
        return _mock_runtime_summary(request)

    if not hasattr(request.state, "runtime_summary"):
        agent_runtime = request.app.state.agent_runtime
        request.state.runtime_summary = await agent_runtime.get_runtime_summary()
    return request.state.runtime_summary


def _mcp_status_for_definition(
    definition: AgentDefinition,
    *,
    mcp_connection_status: dict[str, str],
) -> dict[str, str]:
    return {key: mcp_connection_status.get(key, "unknown") for key in definition.mcp_server_keys}


def _resolve_agent_connection_status(
    request: Request,
    definition: AgentDefinition,
    *,
    runtime_summary: dict | None = None,
) -> str:
    manager = request.app.state.agent_manager
    manager_status = manager.get_agent_health_status()
    if definition.agent_id in manager_status:
        return str(manager_status[definition.agent_id])

    summary = runtime_summary or {}
    remote_status = summary.get("agent_status", {})
    if isinstance(remote_status, dict) and definition.agent_id in remote_status:
        return str(remote_status[definition.agent_id])

    if _runtime_mode(request) == "http":
        return "connected"
    return "unknown"


def _talkable_lookup(request: Request) -> dict[str, bool]:
    if not hasattr(request.state, "talkable_by_agent_id"):
        database_path = getattr(request.app.state, "database_path", None)
        if database_path is None:
            request.state.talkable_by_agent_id = {}
        else:
            request.state.talkable_by_agent_id = build_talkable_by_catalog_agent_id(
                database_path,
                runtime_mode=_runtime_mode(request),
            )
    return request.state.talkable_by_agent_id


def _chat_enabled_for_agent(request: Request, definition: AgentDefinition) -> bool:
    talkable_lookup = _talkable_lookup(request)
    if definition.agent_id in talkable_lookup:
        return talkable_lookup[definition.agent_id]
    return default_talkable_for_local_agent_id(definition.agent_id)


def _agent_payload(
    request: Request,
    definition: AgentDefinition,
    *,
    runtime_summary: dict | None = None,
) -> dict:
    manager = request.app.state.agent_manager

    summary = runtime_summary or {}
    mcp_root = summary.get("mcp", {})
    status = _resolve_agent_connection_status(
        request,
        definition,
        runtime_summary=runtime_summary,
    )
    mcp_status = _mcp_status_for_definition(
        definition,
        mcp_connection_status=mcp_root if isinstance(mcp_root, dict) else {},
    )

    return {
        "id": definition.agent_id,
        "name": definition.name,
        "role": definition.role,
        "mcp_servers": definition.mcp_server_keys,
        "mcp_status": mcp_status,
        "status": status,
        "operation_status": manager.get_operation_status(definition.agent_id),
        "operation_error": manager.get_operation_error(definition.agent_id),
        "operation_detail": manager.get_operation_detail(definition.agent_id),
        "is_system": False,
        "chat_enabled": _chat_enabled_for_agent(request, definition),
    }


@router.get("/agents")
async def list_agents(request: Request) -> list[dict]:
    _sync_http_catalog_if_needed(request)
    manager = request.app.state.agent_manager
    runtime_summary = await _runtime_summary(request)

    return [
        _agent_payload(request, definition, runtime_summary=runtime_summary)
        for definition in manager.agent_definitions
    ]


@router.get("/agents/{agent_id}/tools")
async def list_agent_tools(agent_id: str, request: Request) -> list[dict]:
    if not get_runtime_capabilities(_runtime_mode(request)).agent_tools:
        raise HTTPException(status_code=503, detail=MOCK_RUNTIME_UNAVAILABLE_DETAIL)

    manager = request.app.state.agent_manager
    try:
        manager.get_definition(agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found") from exc

    try:
        return await request.app.state.agent_runtime.list_agent_tools(agent_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Runtime tools lookup failed: {exc}") from exc


@router.get("/health")
async def health(request: Request) -> dict:
    _sync_http_catalog_if_needed(request)
    manager = request.app.state.agent_manager
    runtime_summary = await _runtime_summary(request)
    mcp_status = runtime_summary.get("mcp", {})
    mode = _runtime_mode(request)
    return {
        "status": "ok",
        "runtime_status": manager.get_runtime_status(),
        "mcp": mcp_status if isinstance(mcp_status, dict) else {},
        "agents": list(manager.agents.keys()),
        "agent_status": manager.get_agent_health_status(),
        "runtime_mode": mode,
        "runtime_capabilities": get_runtime_capabilities(mode).as_dict(),
    }
