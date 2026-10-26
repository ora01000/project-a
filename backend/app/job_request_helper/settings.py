"""Static configuration for JOB_REQUEST_HELPER.

mock: in-process LangGraph with PRIVATE_CLOUD_AGENT MCP tools + skills
      (prompt still instructs not to execute tools for real work).
http: external AXIT via agentruntime.local_agent_id=JOB_REQUEST_HELPER.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from backend.app.agents.infra_diagram_prompt import INFRA_ARCHITECTURE_D2_INSTRUCTION
from backend.app.agents.private_cloud_agent import (
    ANSIBLE_CLI_SKILL_NAME,
    ANSIBLE_PLAYBOOK_SKILL_NAME,
    INVENTORY_SQL_SKILL_NAME,
    PRIVATE_CLOUD_MCP_SERVER_KEYS,
)
from backend.app.agents.skill_loader import load_skill
from backend.app.config import PROJECT_ROOT

AGENT_ID = "JOB_REQUEST_HELPER"
AGENT_NAME = "Job Request Helper"

# Prompt path per PLAN (docs/system-prompt/JOB_REQUEST_HELPER.md).
SYSTEM_PROMPT_PATH = PROJECT_ROOT / "docs" / "system-prompt" / "JOB_REQUEST_HELPER.md"

# Mock-mode LLM gateway (http uses external AXIT agent).
HTTP_LLM_BASE_URL = "http://llmgateway.apps.pkvgs-k8s.lguplus.co.kr/v1"
HTTP_LLM_MODEL = "axit/openai/gpt-oss-120b"
HTTP_LLM_API_KEY_ENV = "PRIVATE_LLM_API_KEY"

# Same MCP bindings as PRIVATE_CLOUD_AGENT (local/mock only).
MCP_SERVER_KEYS: list[str] = list(PRIVATE_CLOUD_MCP_SERVER_KEYS)


@lru_cache(maxsize=1)
def build_system_prompt() -> str:
    path = Path(SYSTEM_PROMPT_PATH)
    if not path.is_file():
        raise FileNotFoundError(f"System prompt file not found: {path}")
    base = path.read_text(encoding="utf-8").strip()
    # Append PRIVATE_CLOUD_AGENT skills so the helper knows capability surface.
    skills = "\n\n".join(
        [
            "## inventory_sql skill",
            load_skill(INVENTORY_SQL_SKILL_NAME),
            "## ansible_playbook skill",
            load_skill(ANSIBLE_PLAYBOOK_SKILL_NAME),
            "## ansible_cli skill",
            load_skill(ANSIBLE_CLI_SKILL_NAME),
            INFRA_ARCHITECTURE_D2_INSTRUCTION,
        ]
    )
    return f"{base}\n\n{skills}"


@dataclass(frozen=True)
class JobRequestHelperStaticConfig:
    agent_id: str = AGENT_ID
    agent_name: str = AGENT_NAME
    http_llm_base_url: str = HTTP_LLM_BASE_URL
    http_llm_model: str = HTTP_LLM_MODEL
    http_llm_api_key_env: str = HTTP_LLM_API_KEY_ENV
    mcp_server_keys: tuple[str, ...] = tuple(MCP_SERVER_KEYS)


STATIC_CONFIG = JobRequestHelperStaticConfig()
