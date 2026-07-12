from backend.app.agents.base import AgentDefinition
from backend.app.agents.inventory_tool import INVENTORY_AGENT_ID

INVENTORY_AGENT_MARKER = object()

INVENTORY_AGENT = AgentDefinition(
    agent_id=INVENTORY_AGENT_ID,
    name="인벤토리",
    role="시스템 인벤토리 정보 조회 (ChromaDB)",
    mcp_server_keys=[],
    system_prompt=(
        "You are the Inventory system agent. "
        "Answer questions about system inventory using embedded CSV data stored in ChromaDB. "
        "Provide concise, structured answers in Korean when possible."
    ),
)
