from dataclasses import dataclass
from enum import Enum


class NotifyChannel(str, Enum):
    EMAIL = "email"
    TEAMS = "teams"
    INTEGRATED_CHAT = "integrated_chat"


@dataclass(frozen=True)
class SystemAgentInfo:
    agent_id: str
    name: str
    role: str
    chat_enabled: bool = False


HELPDESK_AGENT_ID = "sys-helpdesk"

HELPDESK_AGENT = SystemAgentInfo(
    agent_id=HELPDESK_AGENT_ID,
    name="헬프데스크",
    role="사용자 질의를 적합한 일반 에이전트에 중계",
    chat_enabled=True,
)

SYSTEM_AGENTS: list[SystemAgentInfo] = []
DASHBOARD_SYSTEM_AGENTS: list[SystemAgentInfo] = []
CONTROL_PLANE_ORCHESTRATION_AGENT_IDS: frozenset[str] = frozenset()
SANDBOX_SYSTEM_AGENT_IDS: frozenset[str] = frozenset()
SYSTEM_AGENT_MARKER = object()


def is_control_plane_orchestration_agent(agent_id: str) -> bool:
    return agent_id in CONTROL_PLANE_ORCHESTRATION_AGENT_IDS


def is_dashboard_system_agent_id(agent_id: str) -> bool:
    return False


def list_dashboard_system_agent_definitions():
    from backend.app.agents.base import AgentDefinition

    return []


def system_agent_to_definition(agent: SystemAgentInfo):
    from backend.app.agents.base import AgentDefinition

    return AgentDefinition(
        agent_id=agent.agent_id,
        name=agent.name,
        role=agent.role,
        mcp_server_keys=[],
        system_prompt=f"System agent: {agent.name}. {agent.role}",
    )
