from fastapi import APIRouter, Request

from backend.app.agents.base import _aggregate_mcp_status
from backend.app.agents.registry import AGENT_DEFINITIONS

router = APIRouter(tags=["agents"])


@router.get("/agents")
async def list_agents(request: Request) -> list[dict]:
    manager = request.app.state.agent_manager
    mcp_status = manager.mcp_manager.connection_status if manager.mcp_manager else {}

    return [
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
        }
        for definition in AGENT_DEFINITIONS
    ]


@router.get("/health")
async def health(request: Request) -> dict:
    manager = request.app.state.agent_manager
    return {
        "status": "ok",
        "llm": manager.llm_status,
        "mcp": manager.mcp_manager.connection_status if manager.mcp_manager else {},
        "agents": list(manager.agents.keys()),
    }
