"""Agent execution manager for the standalone runtime service."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.app.agents.base import AgentDefinition, build_agent, _aggregate_mcp_status
from backend.app.agent_runtime.schemas import AgentDefinitionPayload, payload_to_definition
from backend.app.disabled_features import filter_agent_definitions
from backend.app.mcp.client import MCPClientManager
from backend.app.config import load_settings

logger = logging.getLogger(__name__)


class RuntimeAgentManager:
    """Slim manager: LangGraph agents + MCP on the sandbox runtime."""

    def __init__(self) -> None:
        self.agents: dict[str, Any] = {}
        self.agent_definitions: list[AgentDefinition] = []
        self.agent_definitions_by_id: dict[str, AgentDefinition] = {}
        self.agent_health_status: dict[str, str] = {}
        self.mcp_manager: MCPClientManager | None = None
        self.agent_runtime: Any | None = None

    async def initialize(self, database_path: Path) -> None:
        from backend.app.agents.registry import load_static_agent_definitions

        _, _, mcp_servers, _ = load_settings()
        self.mcp_manager = MCPClientManager(mcp_servers)
        await self.mcp_manager.initialize()

        self.agent_definitions = filter_agent_definitions(load_static_agent_definitions())
        self.agent_definitions_by_id = {
            definition.agent_id: definition for definition in self.agent_definitions
        }
        await self._rebuild_agents()
        await self.refresh_health()

    async def _rebuild_agents(self) -> None:
        if self.mcp_manager is None:
            raise RuntimeError("RuntimeAgentManager is not initialized")

        self.agents.clear()

        for definition in self.agent_definitions:
            try:
                self.agents[definition.agent_id] = await build_agent(definition, self.mcp_manager)
            except Exception as exc:
                logger.exception("Failed to build agent %s: %s", definition.agent_id, exc)

    async def reload_definitions(self, definitions: list[AgentDefinitionPayload]) -> None:
        self.agent_definitions = filter_agent_definitions(
            [payload_to_definition(item) for item in definitions]
        )
        self.agent_definitions_by_id = {
            definition.agent_id: definition for definition in self.agent_definitions
        }
        await self._rebuild_agents()
        await self.refresh_health()

    async def refresh_health(self) -> None:
        statuses: dict[str, str] = {}
        for definition in self.agent_definitions:
            agent_id = definition.agent_id
            if agent_id not in self.agents:
                statuses[agent_id] = "unavailable"
                continue
            if self.mcp_manager is None:
                statuses[agent_id] = "unknown"
                continue
            statuses[agent_id] = _aggregate_mcp_status(
                self.mcp_manager,
                definition.mcp_server_keys,
            )
        self.agent_health_status = statuses

    def get_agent(self, agent_id: str) -> Any:
        if agent_id not in self.agents:
            raise KeyError(agent_id)
        return self.agents[agent_id]

    def get_definition(self, agent_id: str) -> AgentDefinition:
        if agent_id not in self.agent_definitions_by_id:
            raise KeyError(agent_id)
        return self.agent_definitions_by_id[agent_id]

    def get_agent_health_status(self) -> dict[str, str]:
        return dict(self.agent_health_status)
