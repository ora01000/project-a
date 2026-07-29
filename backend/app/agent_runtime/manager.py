"""Agent execution manager for the standalone runtime service."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.app.agents.base import AgentDefinition, build_agent
from backend.app.agents.inventory_agent import INVENTORY_AGENT_MARKER
from backend.app.agents.inventory_tool import INVENTORY_AGENT_ID
from backend.app.agents.system_agents import (
    SANDBOX_SYSTEM_AGENT_IDS,
    SYSTEM_AGENT_MARKER,
    system_agent_to_definition,
)
from backend.app.agent_runtime.schemas import AgentDefinitionPayload, payload_to_definition
from backend.app.mcp.client import MCPClientManager
from backend.app.config import load_settings

logger = logging.getLogger(__name__)


class RuntimeAgentManager:
    """Slim manager: LangGraph agents + MCP + sandbox system agents (helpdesk)."""

    def __init__(self) -> None:
        self.agents: dict[str, Any] = {}
        self.agent_definitions: list[AgentDefinition] = []
        self.agent_definitions_by_id: dict[str, AgentDefinition] = {}
        self.agent_health_status: dict[str, str] = {}
        self.mcp_manager: MCPClientManager | None = None
        self.inventory_service: Any | None = None
        self.agent_runtime: Any | None = None

    def _register_sandbox_system_agents(self) -> None:
        from backend.app.agents.system_agents import SYSTEM_AGENTS

        for sys_agent in SYSTEM_AGENTS:
            if sys_agent.agent_id not in SANDBOX_SYSTEM_AGENT_IDS:
                continue
            definition = system_agent_to_definition(sys_agent)
            self.agent_definitions_by_id[definition.agent_id] = definition
            if not any(item.agent_id == definition.agent_id for item in self.agent_definitions):
                self.agent_definitions.append(definition)
            self.agents[definition.agent_id] = SYSTEM_AGENT_MARKER

    async def initialize(self, database_path: Path) -> None:
        from backend.app.agents.registry import load_agent_definitions

        _, _, mcp_servers, _ = load_settings()
        self.mcp_manager = MCPClientManager(mcp_servers)
        await self.mcp_manager.initialize()

        self.agent_definitions = load_agent_definitions(database_path)
        self.agent_definitions_by_id = {
            definition.agent_id: definition for definition in self.agent_definitions
        }
        await self._rebuild_agents()
        self._register_sandbox_system_agents()
        await self.refresh_health()

    def _inventory_health(self) -> str:
        if self.inventory_service is None:
            return "unknown"
        return self.inventory_service.status

    async def _rebuild_agents(self) -> None:
        if self.mcp_manager is None:
            raise RuntimeError("RuntimeAgentManager is not initialized")

        preserved_system = {
            agent_id: marker
            for agent_id, marker in self.agents.items()
            if agent_id in SANDBOX_SYSTEM_AGENT_IDS
        }
        self.agents.clear()
        self.agents.update(preserved_system)

        for definition in self.agent_definitions:
            if definition.agent_id in SANDBOX_SYSTEM_AGENT_IDS:
                continue
            if definition.agent_id == INVENTORY_AGENT_ID:
                self.agents[definition.agent_id] = INVENTORY_AGENT_MARKER
                continue
            try:
                self.agents[definition.agent_id] = await build_agent(definition, self.mcp_manager)
            except Exception as exc:
                logger.exception("Failed to build agent %s: %s", definition.agent_id, exc)

    async def reload_definitions(self, definitions: list[AgentDefinitionPayload]) -> None:
        self.agent_definitions = [payload_to_definition(item) for item in definitions]
        self.agent_definitions_by_id = {
            definition.agent_id: definition for definition in self.agent_definitions
        }
        await self._rebuild_agents()
        self._register_sandbox_system_agents()
        await self.refresh_health()

    async def refresh_health(self) -> None:
        from backend.app.agents.base import _aggregate_mcp_status

        statuses: dict[str, str] = {}
        for definition in self.agent_definitions:
            agent_id = definition.agent_id
            agent = self.agents.get(agent_id)
            if agent is SYSTEM_AGENT_MARKER:
                statuses[agent_id] = "ready"
                continue
            if agent_id == INVENTORY_AGENT_ID:
                statuses[agent_id] = self._inventory_health()
                continue
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
