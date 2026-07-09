from fastapi import APIRouter, Request

from backend.app.agents.base import _aggregate_mcp_status
from backend.app.agents.registry import AGENT_DEFINITIONS

router = APIRouter(tags=["agents"])


@router.get("/agents")
async def list_agents(request: Request) -> list[dict]:
    manager = request.app.state.agent_manager
    mcp_status = manager.mcp_manager.connection_status if manager.mcp_manager else {}
    token_tracker = manager.token_tracker
    max_context_tokens = manager.max_context_tokens

    agents: list[dict] = []
    for definition in AGENT_DEFINITIONS:
        usage = token_tracker.get_usage(definition.agent_id) if token_tracker else None
        input_tokens = usage.input_tokens if usage else 0
        output_tokens = usage.output_tokens if usage else 0
        total_tokens = usage.total_tokens if usage else 0
        usage_percent = token_tracker.usage_percent(definition.agent_id) if token_tracker else 0.0

        agents.append(
            {
                "id": definition.agent_id,
                "name": definition.name,
                "role": definition.role,
                "mcp_servers": definition.mcp_server_keys,
                "mcp_status": {
                    key: mcp_status.get(key, "unknown") for key in definition.mcp_server_keys
                },
                "status": _aggregate_mcp_status(manager.mcp_manager, definition.mcp_server_keys)
                if manager.mcp_manager
                else "unknown",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "max_context_tokens": max_context_tokens,
                "token_usage_percent": round(usage_percent, 1),
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
    }
