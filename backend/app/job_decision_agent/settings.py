"""Static configuration for JOB_DECISION_AGENT (code-only; no AXIT catalog)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.app.agents.system_prompt_loader import load_system_prompt_template

AGENT_ID = "JOB_DECISION_AGENT"
AGENT_NAME = "Job Decision Agent"

# Same LLM gateway wiring as INFRA_GAP_ANALYSIS.
# Bifrost custom provider "axit"; backend vLLM model remains openai/gpt-oss-120b.
HTTP_LLM_BASE_URL = "http://llmgateway.apps.pkvgs-k8s.lguplus.co.kr/v1"
HTTP_LLM_MODEL = "axit/openai/gpt-oss-120b"
HTTP_LLM_API_KEY_ENV = "PRIVATE_LLM_API_KEY"

_SKILLS_DIR = Path(__file__).resolve().parent / "skills"


def load_job_scope_skill() -> str:
    path = _SKILLS_DIR / "job_scope.md"
    return path.read_text(encoding="utf-8")


def build_system_prompt() -> str:
    skill = load_job_scope_skill()
    return load_system_prompt_template(AGENT_ID, skill=skill)


SYSTEM_PROMPT = build_system_prompt()


@dataclass(frozen=True)
class JobDecisionStaticConfig:
    agent_id: str = AGENT_ID
    agent_name: str = AGENT_NAME
    http_llm_base_url: str = HTTP_LLM_BASE_URL
    http_llm_model: str = HTTP_LLM_MODEL
    http_llm_api_key_env: str = HTTP_LLM_API_KEY_ENV
    system_prompt: str = SYSTEM_PROMPT


STATIC_CONFIG = JobDecisionStaticConfig()
