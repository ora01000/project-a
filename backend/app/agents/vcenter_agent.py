from backend.app.agents.base import AgentDefinition
from backend.app.agents.system_prompt_loader import load_system_prompt

VCENTER_AGENT = AgentDefinition(
    agent_id="vcenter",
    name="VMware Agent",
    role="VMware vCenter 정보 조회",
    mcp_server_keys=["vcenter"],
    system_prompt=load_system_prompt("vcenter"),
)
