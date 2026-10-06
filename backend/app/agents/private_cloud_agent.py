"""Private Cloud integrated agent (OKD / KubeVirt / vSphere / NSX-T + inventory + ansible)."""

from backend.app.agents.base import AgentDefinition
from backend.app.agents.infra_diagram_prompt import INFRA_ARCHITECTURE_D2_INSTRUCTION
from backend.app.agents.skill_loader import load_skill
from backend.app.agents.system_prompt_loader import load_system_prompt

PRIVATE_CLOUD_AGENT_ID = "PRIVATE_CLOUD_AGENT"
PRIVATE_CLOUD_AGENT_NAME = "Private 클라우드 통합 에이전트"
INVENTORY_SQL_SKILL_NAME = "inventory_sql"
ANSIBLE_PLAYBOOK_SKILL_NAME = "ansible_playbook"
ANSIBLE_CLI_SKILL_NAME = "ansible_cli"

# mcp-okd / mcp-kubevirt / mcp-vsphere / mcp-nsxt / mcp-ansible (+ inventory)
PRIVATE_CLOUD_MCP_SERVER_KEYS = [
    "kubernetes",
    "kubevirt",
    "vcenter",
    "nsxt",
    "inventory",
    "ansible",
]


def _build_system_prompt() -> str:
    # Use replace — skill/prompt bodies may contain unrelated `{...}` braces.
    base = (
        load_system_prompt(PRIVATE_CLOUD_AGENT_ID)
        .replace("{inventory_skill}", load_skill(INVENTORY_SQL_SKILL_NAME))
        .replace("{ansible_playbook_skill}", load_skill(ANSIBLE_PLAYBOOK_SKILL_NAME))
        .replace("{ansible_cli_skill}", load_skill(ANSIBLE_CLI_SKILL_NAME))
    )
    return f"{base}\n\n{INFRA_ARCHITECTURE_D2_INSTRUCTION}"


PRIVATE_CLOUD_AGENT = AgentDefinition(
    agent_id=PRIVATE_CLOUD_AGENT_ID,
    name=PRIVATE_CLOUD_AGENT_NAME,
    role="Private 클라우드(OKD/KubeVirt/vSphere/NSX-T)·인벤토리·Ansible 작성/검증/실행",
    mcp_server_keys=list(PRIVATE_CLOUD_MCP_SERVER_KEYS),
    system_prompt=_build_system_prompt(),
)
