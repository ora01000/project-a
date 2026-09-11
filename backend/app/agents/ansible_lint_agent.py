"""Mock-only Ansible playbook authoring / lint agent (Ansible 2.9.18)."""

from __future__ import annotations

from backend.app.agents.base import AgentDefinition
from backend.app.agents.system_prompt_loader import load_system_prompt

ANSIBLE_LINT_LOCAL_AGENT_ID = "ansible-lint"
ANSIBLE_LINT_MCP_SERVER_KEY = "ansible_lint"

ANSIBLE_LINT_AGENT = AgentDefinition(
    agent_id=ANSIBLE_LINT_LOCAL_AGENT_ID,
    name="Ansible Playbook 검토",
    role="Ansible 2.9.18 playbook 생성, 검증",
    mcp_server_keys=[ANSIBLE_LINT_MCP_SERVER_KEY],
    system_prompt=load_system_prompt(ANSIBLE_LINT_LOCAL_AGENT_ID),
)
