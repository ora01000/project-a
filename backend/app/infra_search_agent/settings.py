"""Static configuration for INFRA_SEARCH_AGENT (mock inventory search)."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.agents.skill_loader import read_skill
from backend.app.agents.system_prompt_loader import read_system_prompt

AGENT_ID = "INFRA_SEARCH_AGENT"
AGENT_NAME = "Infra Search Agent"
INVENTORY_SQL_SKILL_NAME = "inventory_sql"
MCP_SERVER_KEY = "inventory"

# Inventory MCP endpoints by runtime mode (mock | http)
MCP_URL_MOCK = "http://inventory-mcp.ora01000.pe.kr:32716/mcp"
MCP_URL_HTTP = "http://inventory-mcp.ora01000.pe.kr:32716/mcp"
MCP_TRANSPORT = "http"

# Same LLM gateway wiring as INFRA_GAP_ANALYSIS / JOB_DECISION_AGENT.
HTTP_LLM_BASE_URL = "http://llmgateway.apps.pkvgs-k8s.lguplus.co.kr/v1"
HTTP_LLM_MODEL = "axit/openai/gpt-oss-120b"
HTTP_LLM_API_KEY_ENV = "PRIVATE_LLM_API_KEY"

ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "getInventoryList",
        "getInventorySchema",
        "readDataUsingSQL",
    }
)


def load_inventory_sql_skill() -> str:
    return read_skill(INVENTORY_SQL_SKILL_NAME)


def build_system_prompt() -> str:
    """Prompt + inventory_sql skill (re-read on each agent init)."""
    skill = load_inventory_sql_skill()
    return read_system_prompt(AGENT_ID).format(skill=skill)


@dataclass(frozen=True)
class InfraSearchStaticConfig:
    agent_id: str = AGENT_ID
    agent_name: str = AGENT_NAME
    mcp_server_key: str = MCP_SERVER_KEY
    mcp_url_mock: str = MCP_URL_MOCK
    mcp_url_http: str = MCP_URL_HTTP
    mcp_transport: str = MCP_TRANSPORT
    http_llm_base_url: str = HTTP_LLM_BASE_URL
    http_llm_model: str = HTTP_LLM_MODEL
    http_llm_api_key_env: str = HTTP_LLM_API_KEY_ENV


STATIC_CONFIG = InfraSearchStaticConfig()


def mcp_url_for_mode(runtime_mode: str) -> str:
    mode = (runtime_mode or "mock").strip().lower()
    if mode == "local":
        mode = "mock"
    if mode == "http":
        return STATIC_CONFIG.mcp_url_http
    return STATIC_CONFIG.mcp_url_mock
