"""Shared helpers for listing tools available to an agent definition."""

from __future__ import annotations

import logging
from typing import Any

from backend.app.agents.base import AgentDefinition
from backend.app.agents.inventory_tool import INVENTORY_AGENT_ID, QUERY_INVENTORY_TOOL_NAME

logger = logging.getLogger(__name__)


async def list_tools_for_definition(
    agent_manager: Any | None,
    definition: AgentDefinition,
) -> list[dict[str, str]]:
    tools: list[dict[str, str]] = []
    if definition.agent_id == INVENTORY_AGENT_ID:
        tools.append(
            {
                "name": QUERY_INVENTORY_TOOL_NAME,
                "description": "Query the inventory database",
            }
        )

    mcp_manager = getattr(agent_manager, "mcp_manager", None) if agent_manager is not None else None
    if mcp_manager is not None and definition.mcp_server_keys:
        try:
            for tool in await mcp_manager.get_tools_for_servers(definition.mcp_server_keys):
                tools.append(
                    {
                        "name": tool.name,
                        "description": getattr(tool, "description", "") or "",
                    }
                )
        except Exception as exc:
            logger.warning("Failed to list tools for %s: %s", definition.agent_id, exc)
    return tools
