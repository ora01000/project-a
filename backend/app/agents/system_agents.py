from dataclasses import dataclass
from enum import Enum

from backend.app.agents.base import AgentDefinition

JOB_PLANNING_AGENT_ID = "sys-job-planning"
JOB_EXECUTION_AGENT_ID = "sys-job-execution"
INVENTORY_AGENT_ID = "sys-inventory"
WHATAP_EVENT_AGENT_ID = "sys-whatap-events"
HELPDESK_AGENT_ID = "sys-helpdesk"

SYSTEM_AGENT_MARKER = object()


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


JOB_PLANNING_AGENT = SystemAgentInfo(
    agent_id=JOB_PLANNING_AGENT_ID,
    name="작업 분석/계획",
    role="작업 요청서 접수 및 실행 계획 수립",
)

JOB_EXECUTION_AGENT = SystemAgentInfo(
    agent_id=JOB_EXECUTION_AGENT_ID,
    name="작업 수행",
    role="승인된 작업을 계획대로 수행",
)

INVENTORY_SYSTEM_AGENT = SystemAgentInfo(
    agent_id=INVENTORY_AGENT_ID,
    name="인벤토리",
    role="ChromaDB 기반 시스템 인벤토리 조회",
)

WHATAP_EVENT_AGENT = SystemAgentInfo(
    agent_id=WHATAP_EVENT_AGENT_ID,
    name="Whatap 이벤트 수신",
    role="Whatap 외부 시스템 webhook 이벤트 수신",
)

HELPDESK_AGENT = SystemAgentInfo(
    agent_id=HELPDESK_AGENT_ID,
    name="헬프데스크",
    role="사용자 질의를 적합한 일반/인벤토리 에이전트에 중계",
    chat_enabled=True,
)

SYSTEM_AGENTS: list[SystemAgentInfo] = [
    JOB_PLANNING_AGENT,
    JOB_EXECUTION_AGENT,
    INVENTORY_SYSTEM_AGENT,
    WHATAP_EVENT_AGENT,
    HELPDESK_AGENT,
]

# DB/registry inventory agent already has a tile; keep these for dashboard display.
DASHBOARD_SYSTEM_AGENTS: list[SystemAgentInfo] = [
    JOB_PLANNING_AGENT,
    JOB_EXECUTION_AGENT,
    WHATAP_EVENT_AGENT,
    HELPDESK_AGENT,
]


def system_agent_to_definition(agent: SystemAgentInfo) -> AgentDefinition:
    return AgentDefinition(
        agent_id=agent.agent_id,
        name=agent.name,
        role=agent.role,
        mcp_server_keys=[],
        system_prompt=f"System agent: {agent.name}. {agent.role}",
    )


def list_dashboard_system_agent_definitions() -> list[AgentDefinition]:
    return [system_agent_to_definition(agent) for agent in DASHBOARD_SYSTEM_AGENTS]


def is_dashboard_system_agent_id(agent_id: str) -> bool:
    return any(agent.agent_id == agent_id for agent in DASHBOARD_SYSTEM_AGENTS)


def is_chat_enabled_system_agent_id(agent_id: str) -> bool:
    return any(agent.agent_id == agent_id and agent.chat_enabled for agent in SYSTEM_AGENTS)


def get_system_agent_info(agent_id: str) -> SystemAgentInfo | None:
    return next((agent for agent in SYSTEM_AGENTS if agent.agent_id == agent_id), None)
