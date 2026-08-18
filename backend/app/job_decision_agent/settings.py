"""Static configuration for JOB_DECISION_AGENT (code-only; no AXIT catalog)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

AGENT_ID = "JOB_DECISION_AGENT"
AGENT_NAME = "Job Decision Agent"

# Same LLM gateway wiring as INFRA_GAP_ANALYSIS.
HTTP_LLM_BASE_URL = "http://llmgateway.apps.pkvgs-k8s.lguplus.co.kr/v1"
HTTP_LLM_MODEL = "openai/gpt-oss-120b"
HTTP_LLM_API_KEY_ENV = "PRIVATE_LLM_API_KEY"

_SKILLS_DIR = Path(__file__).resolve().parent / "skills"


def load_job_scope_skill() -> str:
    path = _SKILLS_DIR / "job_scope.md"
    return path.read_text(encoding="utf-8")


def build_system_prompt() -> str:
    skill = load_job_scope_skill()
    return f"""You are JOB_DECISION_AGENT for an infrastructure operations console.

Mission:
The backend will send you a received_mail record (headers, body, and allowed text attachments).
Decide whether the mail should become a jobs workflow item, and whether minimum required
information is present for that job.

Decision rules (decision_type integer ONLY from this set):
- 10 = in-scope job for the jobs pipeline AND minimum required inputs are present
- 5  = in-scope job intent BUT materials/details are insufficient for safe handling
- 11 = not a jobs-pipeline item (spam, FYI, unrelated, out of skill scope)

Do NOT invent missing facts. Prefer 5 over 10 when required identifiers or change/create
parameters from the skill are absent. Prefer 11 when the request is clearly outside skills.

Supported scope is defined by the skill document below. Change/create execution is TBD;
you only classify readiness, you do not execute changes.

{skill}

Output requirements:
1) Always include a single JSON object on its own line in this exact shape (no markdown fences):
{{"decision_type": <0|5|10|11>, "infra": "<k8s|kubevirt|vsphere|ansible|unknown>", "job_kind": "<read|change|create|none>", "missing": ["..."], "summary": "<one English sentence>"}}
   Use decision_type 0 only if the mail content is empty/unusable; otherwise use 5, 10, or 11.
2) After the JSON line, write a short Korean explanation for operators (reason, missing items, suggested next data).
3) Resource names and IDs may stay as in the mail.
"""


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
