from backend.app.agents.base import AgentDefinition
from backend.app.agents.system_prompt_loader import load_system_prompt

ANSIBLE_AGENT = AgentDefinition(
    agent_id="ansible",
    name="Ansible Agent",
    role="Ansible 인벤토리 및 플레이북 정보 조회",
    mcp_server_keys=["ansible"],
    system_prompt=load_system_prompt("ansible"),
)
