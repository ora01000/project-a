from fastapi import APIRouter, HTTPException, Request

from backend.app.agents.base import AgentDefinition
from backend.app.services.agent_runtime_client import (
    MOCK_RUNTIME_UNAVAILABLE_DETAIL,
    get_runtime_capabilities,
    normalize_runtime_mode,
)

router = APIRouter(tags=["agents"])


def _runtime_mode(request: Request) -> str:
    return normalize_runtime_mode(getattr(request.app.state, "agent_runtime_mode", "mock"))


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


def _agent_payload(
    request: Request,
    definition: AgentDefinition,
    *,
    runtime_summary: dict | None = None,
) -> dict:
    manager = request.app.state.agent_manager

    summary = runtime_summary or {}
    agent_status = summary.get("agent_status", {})
    mcp_root = summary.get("mcp", {})
    status = str(agent_status.get(definition.agent_id, "unknown"))
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
        "chat_enabled": True,
    }


@router.get("/agents")
async def list_agents(request: Request) -> list[dict]:
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
