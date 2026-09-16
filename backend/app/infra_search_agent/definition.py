"""Mock-runtime catalog entry for INFRA_SEARCH_AGENT (execution via InfraSearchAgentService)."""

from __future__ import annotations

from backend.app.agents.base import AgentDefinition
from backend.app.infra_search_agent.settings import (
    AGENT_ID,
    AGENT_NAME,
    MCP_SERVER_KEY,
)

INFRA_SEARCH_SERVICE_MARKER = object()

INFRA_SEARCH_AGENT = AgentDefinition(
    agent_id=AGENT_ID,
    name=AGENT_NAME,
    role="SQLite 인벤토리 MCP 기반 자산 검색 (getInventoryList, getInventorySchema, readDataUsingSQL)",
    mcp_server_keys=[MCP_SERVER_KEY],
    system_prompt="",
)


def is_infra_search_agent_id(agent_id: str) -> bool:
    return agent_id.strip() == AGENT_ID
