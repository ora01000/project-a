from backend.app.agents.ansible_agent import ANSIBLE_AGENT
from pathlib import Path

from backend.app.agents.base import AgentDefinition
from backend.app.agents.inventory_agent import INVENTORY_AGENT
from backend.app.agents.k8s_agent import K8S_CLUSTER_AGENTS
from backend.app.agents.kubevirt_agent import KUBEVIRT_AGENT
from backend.app.agents.vcenter_agent import VCENTER_AGENT

AGENT_DEFINITIONS: list[AgentDefinition] = [
    *K8S_CLUSTER_AGENTS,
    KUBEVIRT_AGENT,
    VCENTER_AGENT,
    ANSIBLE_AGENT,
    INVENTORY_AGENT,
]

AGENT_DEFINITIONS_BY_ID: dict[str, AgentDefinition] = {
    definition.agent_id: definition for definition in AGENT_DEFINITIONS
}


def load_agent_definitions(database_path: str | Path) -> list[AgentDefinition]:
    from backend.app.db.agents import list_agent_definitions

    return list_agent_definitions(database_path)
