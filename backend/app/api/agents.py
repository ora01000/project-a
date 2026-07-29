from fastapi import APIRouter, HTTPException, Request

from backend.app.agents.base import AgentDefinition
from backend.app.agents.system_agents import (
    is_chat_enabled_system_agent_id,
    is_control_plane_orchestration_agent,
)
from backend.app.services.agent_runtime_client import normalize_runtime_mode

router = APIRouter(tags=["agents"])


def _runtime_mode(request: Request) -> str:
    return normalize_runtime_mode(getattr(request.app.state, "agent_runtime_mode", "mock"))


async def _runtime_summary(request: Request) -> dict:
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
    is_system: bool,
    runtime_summary: dict | None = None,
) -> dict:
    manager = request.app.state.agent_manager
    token_tracker = manager.token_tracker
    usage = token_tracker.get_usage(definition.agent_id) if token_tracker else None

    if is_control_plane_orchestration_agent(definition.agent_id):
        status = "ready"
        mcp_status = _mcp_status_for_definition(definition, mcp_connection_status={})
    else:
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
        "input_tokens": usage.input_tokens if usage else 0,
        "output_tokens": usage.output_tokens if usage else 0,
        "is_system": is_system,
        "chat_enabled": (not is_system) or is_chat_enabled_system_agent_id(definition.agent_id),
    }


@router.get("/agents")
async def list_agents(request: Request) -> list[dict]:
    manager = request.app.state.agent_manager
    runtime_summary = await _runtime_summary(request)

    agents: list[dict] = [
        _agent_payload(request, definition, is_system=False, runtime_summary=runtime_summary)
        for definition in manager.agent_definitions
    ]
    agents.extend(
        _agent_payload(request, definition, is_system=True, runtime_summary=runtime_summary)
        for definition in manager.system_agent_definitions
    )
    return agents


@router.get("/agents/{agent_id}/tools")
async def list_agent_tools(agent_id: str, request: Request) -> list[dict]:
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
        "llm": manager.llm_status,
        "mcp": mcp_status if isinstance(mcp_status, dict) else {},
        "agents": list(manager.agents.keys()),
        "agent_status": manager.get_agent_health_status(),
        "runtime_mode": mode,
    }
