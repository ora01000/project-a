from pathlib import Path

from backend.app.agents.ansible_agent import ANSIBLE_AGENT
from backend.app.agents.ansible_lint_agent import ANSIBLE_LINT_AGENT
from backend.app.agents.base import AgentDefinition
from backend.app.agents.k8s_agent import K8S_CLUSTER_AGENTS
from backend.app.agents.kubevirt_agent import KUBEVIRT_AGENT
from backend.app.agents.mock_platform_agents import (
    MOCK_PLATFORM_AGENT_IDS,
    load_mock_platform_agent_definitions,
)
from backend.app.agents.vcenter_agent import VCENTER_AGENT
from backend.app.db.agentruntime import catalog_agent_id, list_agentruntime_records

AGENT_DEFINITIONS: list[AgentDefinition] = [
    *K8S_CLUSTER_AGENTS,
    KUBEVIRT_AGENT,
    VCENTER_AGENT,
    ANSIBLE_AGENT,
    ANSIBLE_LINT_AGENT,
]

AGENT_DEFINITIONS_BY_ID: dict[str, AgentDefinition] = {
    definition.agent_id: definition for definition in AGENT_DEFINITIONS
}


def load_static_agent_definitions() -> list[AgentDefinition]:
    """Built-in agent prompts and MCP bindings for local Runtime(mock) testing."""
    return list(AGENT_DEFINITIONS)


def load_mock_runtime_definitions(database_path: str | Path) -> list[AgentDefinition]:
    """Static mock agents plus mock-platform orchestrator catalog entries."""
    static_ids = set(AGENT_DEFINITIONS_BY_ID.keys())
    definitions = load_static_agent_definitions()
    for definition in load_mock_platform_agent_definitions():
        if definition.agent_id not in static_ids:
            definitions.append(definition)
    return definitions


def load_server_agent_definitions(database_path: str | Path) -> list[AgentDefinition]:
    """Agent catalog from agentruntime for server/external delegation."""
    definitions: list[AgentDefinition] = []
    for record in list_agentruntime_records(database_path, runtime_mode="http"):
        definitions.append(
            AgentDefinition(
                agent_id=catalog_agent_id(record),
                name=record.agent_name,
                role=record.description,
                mcp_server_keys=[],
                system_prompt="",
            ),
        )
    return definitions
