from backend.app.agents.base import AgentDefinition
from backend.app.agents.skill_loader import load_skill
from backend.app.agents.system_prompt_loader import load_system_prompt

ANSIBLE_CLI_SKILL_NAME = "ansible_cli"


def _build_system_prompt() -> str:
    return load_system_prompt("ansible").replace(
        "{ansible_cli_skill}",
        load_skill(ANSIBLE_CLI_SKILL_NAME),
    )


ANSIBLE_AGENT = AgentDefinition(
    agent_id="ansible",
    name="Ansible Agent",
    role="Ansible 2.9 플레이북 lint/check/run 및 인벤토리 관리",
    mcp_server_keys=["ansible"],
    system_prompt=_build_system_prompt(),
)
