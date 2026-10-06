"""Mock-only Ansible playbook authoring / lint / check / run agent (Ansible 2.9)."""

from __future__ import annotations

from backend.app.agents.base import AgentDefinition
from backend.app.agents.skill_loader import load_skill
from backend.app.agents.system_prompt_loader import load_system_prompt

ANSIBLE_LINT_LOCAL_AGENT_ID = "ansible-lint"
ANSIBLE_MCP_SERVER_KEY = "ansible"
ANSIBLE_PLAYBOOK_SKILL_NAME = "ansible_playbook"
ANSIBLE_CLI_SKILL_NAME = "ansible_cli"


def _build_system_prompt() -> str:
    return (
        load_system_prompt(ANSIBLE_LINT_LOCAL_AGENT_ID)
        .replace("{ansible_playbook_skill}", load_skill(ANSIBLE_PLAYBOOK_SKILL_NAME))
        .replace("{ansible_cli_skill}", load_skill(ANSIBLE_CLI_SKILL_NAME))
    )


ANSIBLE_LINT_AGENT = AgentDefinition(
    agent_id=ANSIBLE_LINT_LOCAL_AGENT_ID,
    name="Ansible Playbook 검토",
    role="Ansible 2.9 playbook 작성·검증(lint)·check/run",
    mcp_server_keys=[ANSIBLE_MCP_SERVER_KEY],
    system_prompt=_build_system_prompt(),
)
