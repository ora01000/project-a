"""Static configuration for INFRA_GAP_ANALYSIS (code-only; API key from env)."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.agents.system_prompt_loader import read_system_prompt
from backend.app.config import _env_setting

AGENT_ID = "INFRA_GAP_ANALYSIS"
AGENT_NAME = "Infra Gap Analysis"
MCP_SERVER_KEY = "postgresql"

# MCP endpoints by runtime mode (mock | http)
MCP_URL_MOCK = "http://localhost:30800/mcp"
MCP_URL_HTTP = "http://pgdb-mcp.mcps.svc.cluster.local:8000/mcp"
MCP_TRANSPORT = "http"

# HTTP-mode LLM gateway (OpenAI-compatible). Mock mode reuses the existing control-plane LLM.
# Bifrost splits model on the first "/": provider/model. HF id openai/gpt-oss-120b must be
# prefixed with the custom provider so vLLM still receives openai/gpt-oss-120b.
HTTP_LLM_BASE_URL = "http://llmgateway.apps.pkvgs-k8s.lguplus.co.kr/v1"
HTTP_LLM_MODEL = "axit/openai/gpt-oss-120b"
HTTP_LLM_API_KEY_ENV = "PRIVATE_LLM_API_KEY"


def http_llm_api_key() -> str:
    """Gateway API key. URL/model stay in code; only the secret comes from env."""
    return _env_setting(HTTP_LLM_API_KEY_ENV)


def build_system_prompt() -> str:
    """Read the latest prompt from docs/system-prompt on each agent initialization."""
    return read_system_prompt(AGENT_ID)


@dataclass(frozen=True)
class InfraGapAnalysisStaticConfig:
    agent_id: str = AGENT_ID
    agent_name: str = AGENT_NAME
    mcp_server_key: str = MCP_SERVER_KEY
    mcp_url_mock: str = MCP_URL_MOCK
    mcp_url_http: str = MCP_URL_HTTP
    mcp_transport: str = MCP_TRANSPORT
    http_llm_base_url: str = HTTP_LLM_BASE_URL
    http_llm_model: str = HTTP_LLM_MODEL
    http_llm_api_key_env: str = HTTP_LLM_API_KEY_ENV


STATIC_CONFIG = InfraGapAnalysisStaticConfig()


def mcp_url_for_mode(runtime_mode: str) -> str:
    mode = (runtime_mode or "mock").strip().lower()
    if mode == "local":
        mode = "mock"
    if mode == "http":
        return STATIC_CONFIG.mcp_url_http
    return STATIC_CONFIG.mcp_url_mock
