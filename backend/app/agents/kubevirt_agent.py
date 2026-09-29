from backend.app.agents.base import AgentDefinition
from backend.app.agents.infra_diagram_prompt import INFRA_ARCHITECTURE_D2_INSTRUCTION
from backend.app.agents.system_prompt_loader import load_system_prompt

KUBEVIRT_AGENT = AgentDefinition(
    agent_id="kubevirt",
    name="KubeVirt VM Agent",
    role="KubeVirt VM 정보 조회",
    mcp_server_keys=["kubevirt"],
    system_prompt=f"{load_system_prompt('kubevirt')}\n\n{INFRA_ARCHITECTURE_D2_INSTRUCTION}",
)
