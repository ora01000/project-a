"""Private Cloud integrated agent (OKD / KubeVirt / vSphere / NSX-T + inventory)."""

from backend.app.agents.base import AgentDefinition
from backend.app.agents.infra_diagram_prompt import INFRA_ARCHITECTURE_D2_INSTRUCTION
from backend.app.agents.skill_loader import load_skill
from backend.app.agents.system_prompt_loader import load_system_prompt

PRIVATE_CLOUD_AGENT_ID = "PRIVATE_CLOUD_AGENT"
PRIVATE_CLOUD_AGENT_NAME = "Private 클라우드 통합 에이전트"
INVENTORY_SQL_SKILL_NAME = "inventory_sql"

# mcp-okd / mcp-kubevirt / mcp-vsphere / mcp-nsxt (+ inventory for inventory_sql skill)
PRIVATE_CLOUD_MCP_SERVER_KEYS = [
    "kubernetes",
    "kubevirt",
    "vcenter",
    "nsxt",
    "inventory",
]


def _build_system_prompt() -> str:
    skill = load_skill(INVENTORY_SQL_SKILL_NAME)
    base = load_system_prompt(PRIVATE_CLOUD_AGENT_ID).format(skill=skill)
    return f"{base}\n\n{INFRA_ARCHITECTURE_D2_INSTRUCTION}"


PRIVATE_CLOUD_AGENT = AgentDefinition(
    agent_id=PRIVATE_CLOUD_AGENT_ID,
    name=PRIVATE_CLOUD_AGENT_NAME,
    role="Private 클라우드(OKD/KubeVirt/vSphere/NSX-T) 및 인벤토리 통합 조회",
    mcp_server_keys=list(PRIVATE_CLOUD_MCP_SERVER_KEYS),
    system_prompt=_build_system_prompt(),
)
