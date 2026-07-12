from fastapi import APIRouter, Request

from backend.app.agents.base import _aggregate_mcp_status
from backend.app.agents.inventory_tool import INVENTORY_AGENT_ID

router = APIRouter(tags=["agents"])


@router.get("/agents")
async def list_agents(request: Request) -> list[dict]:
    manager = request.app.state.agent_manager
    mcp_status = manager.mcp_manager.connection_status if manager.mcp_manager else {}
    token_tracker = manager.token_tracker

    agents: list[dict] = []
    for definition in manager.agent_definitions:
        usage = token_tracker.get_usage(definition.agent_id) if token_tracker else None
        input_tokens = usage.input_tokens if usage else 0
        output_tokens = usage.output_tokens if usage else 0

        agents.append(
            {
                "id": definition.agent_id,
                "name": definition.name,
                "role": definition.role,
                "mcp_servers": definition.mcp_server_keys,
                "mcp_status": {
                    key: mcp_status.get(key, "unknown") for key in definition.mcp_server_keys
                },
                "status": (
                    manager.get_inventory_health_status()
                    if definition.agent_id == INVENTORY_AGENT_ID
                    else (
                        _aggregate_mcp_status(manager.mcp_manager, definition.mcp_server_keys)
                        if manager.mcp_manager
                        else "unknown"
                    )
                ),
                "operation_status": manager.get_operation_status(definition.agent_id),
                "operation_error": manager.get_operation_error(definition.agent_id),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }
        )

    return agents


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
