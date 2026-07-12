from dataclasses import dataclass
from enum import Enum

JOB_PLANNING_AGENT_ID = "sys-job-planning"
JOB_EXECUTION_AGENT_ID = "sys-job-execution"
INVENTORY_AGENT_ID = "sys-inventory"
WHATAP_EVENT_AGENT_ID = "sys-whatap-events"


class NotifyChannel(str, Enum):
    EMAIL = "email"
    TEAMS = "teams"
    INTEGRATED_CHAT = "integrated_chat"


@dataclass(frozen=True)
class SystemAgentInfo:
    agent_id: str
    name: str
    role: str


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

SYSTEM_AGENTS: list[SystemAgentInfo] = [
    JOB_PLANNING_AGENT,
    JOB_EXECUTION_AGENT,
    INVENTORY_SYSTEM_AGENT,
    WHATAP_EVENT_AGENT,
]
