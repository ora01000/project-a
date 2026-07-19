from fastapi import APIRouter, HTTPException, Request

from backend.app.agents.base import AgentDefinition, _aggregate_mcp_status
from backend.app.agents.inventory_tool import INVENTORY_AGENT_ID, QUERY_INVENTORY_TOOL_NAME
from backend.app.agents.system_agents import (
    is_chat_enabled_system_agent_id,
    is_dashboard_system_agent_id,
)

router = APIRouter(tags=["agents"])


def _agent_payload(
    request: Request,
    definition: AgentDefinition,
    *,
    is_system: bool,
) -> dict:
    manager = request.app.state.agent_manager
    mcp_status = manager.mcp_manager.connection_status if manager.mcp_manager else {}
    token_tracker = manager.token_tracker
    usage = token_tracker.get_usage(definition.agent_id) if token_tracker else None

    if definition.agent_id == INVENTORY_AGENT_ID:
        status = manager.get_inventory_health_status()
    elif is_system or is_dashboard_system_agent_id(definition.agent_id):
        status = "ready"
    elif manager.mcp_manager:
        status = _aggregate_mcp_status(manager.mcp_manager, definition.mcp_server_keys)
    else:
        status = "unknown"

    return {
        "id": definition.agent_id,
        "name": definition.name,
        "role": definition.role,
        "mcp_servers": definition.mcp_server_keys,
        "mcp_status": {
            key: mcp_status.get(key, "unknown") for key in definition.mcp_server_keys
        },
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

    agents: list[dict] = [
        _agent_payload(request, definition, is_system=False)
        for definition in manager.agent_definitions
    ]
    agents.extend(
        _agent_payload(request, definition, is_system=True)
        for definition in manager.system_agent_definitions
    )
    return agents


@router.get("/agents/{agent_id}/tools")
async def list_agent_tools(agent_id: str, request: Request) -> list[dict]:
    manager = request.app.state.agent_manager
    try:
        definition = manager.get_definition(agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found") from exc

    tools: list[dict[str, str]] = []
    if agent_id == INVENTORY_AGENT_ID:
        tools.append(
            {
                "name": QUERY_INVENTORY_TOOL_NAME,
                "description": "Query the inventory database",
            }
        )

    if manager.mcp_manager and definition.mcp_server_keys:
        for tool in await manager.mcp_manager.get_tools_for_servers(definition.mcp_server_keys):
            tools.append(
                {
                    "name": tool.name,
                    "description": getattr(tool, "description", "") or "",
                }
            )

    return tools


@router.get("/health")
async def health(request: Request) -> dict:
    manager = request.app.state.agent_manager
    return {
        "status": "ok",
        "llm": manager.llm_status,
        "mcp": manager.mcp_manager.connection_status if manager.mcp_manager else {},
        "agents": list(manager.agents.keys()),
        "agent_status": manager.get_agent_health_status(),
    }
