"""Standalone JOB_DECISION_AGENT — static LangGraph agent (no AXIT / mock catalog)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from backend.app.agents.base import AgentInvokeResult, invoke_agent
from backend.app.config import resolve_agent_runtime_mode
from backend.app.db.received_mail import (
    DECISION_TYPE_INSUFFICIENT,
    DECISION_TYPE_JOB,
    DECISION_TYPE_NON_JOB,
    DECISION_TYPE_PENDING,
    VALID_DECISION_TYPES,
    get_received_mail_by_uuid,
    update_decision_type,
)
from backend.app.job_decision_agent.settings import STATIC_CONFIG, build_system_prompt
from backend.app.services.agent_runtime_client import normalize_runtime_mode
from backend.app.services.received_mail_attachments import resolve_attachment_file

logger = logging.getLogger(__name__)

_JSON_LINE = re.compile(
    r"\{[^{}]*\"decision_type\"\s*:\s*\d+[^{}]*\}",
    re.DOTALL,
)


def _build_llm(runtime_mode: str) -> ChatOpenAI:
    from backend.app.logging.prompt_debug import wrap_llm_for_prompt_debug

    if runtime_mode == "http":
        llm: ChatOpenAI = ChatOpenAI(
            base_url=STATIC_CONFIG.http_llm_base_url,
            api_key=STATIC_CONFIG.http_llm_api_key,
            model=STATIC_CONFIG.http_llm_model,
            temperature=0,
            streaming=False,
            disable_streaming="tool_calling",
        )
    else:
        from backend.app.llm.factory import get_llm

        llm = get_llm()

    return wrap_llm_for_prompt_debug(
        llm,
        agent_id=STATIC_CONFIG.agent_id,
        agent_name=STATIC_CONFIG.agent_name,
    )


def _read_attachment_text(mail_uuid: str, filename: str, *, max_chars: int = 20000) -> str:
    path = resolve_attachment_file(mail_uuid, filename)
    if not path.is_file():
        return f"[missing attachment file: {filename}]"
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    if len(text) > max_chars:
        return text[:max_chars] + "\n...[truncated]..."
    return text


def build_mail_decision_message(
    database_path,
    mail_uuid: str,
) -> tuple[str, str]:
    """Return (user_message, mail_uuid). Raises ValueError if mail missing."""
    record = get_received_mail_by_uuid(database_path, mail_uuid)
    if record is None:
        raise ValueError(f"received_mail not found: {mail_uuid}")

    parts: list[str] = [
        "Evaluate this received_mail record for jobs pipeline classification.",
        f"uuid: {record.uuid}",
        f"subject: {record.subject}",
        f"from: {record.from_address}",
        f"to: {record.to_addresses}",
        f"cc: {record.cc_addresses}",
        f"received_at: {record.received_at}",
        f"message_id: {record.message_id}",
        "",
        "=== body_text ===",
        record.body_text or "(empty)",
        "",
    ]
    if record.attachment_names:
        parts.append("=== attachments (text) ===")
        for name in record.attachment_names:
            parts.append(f"--- file: {name} ---")
            try:
                parts.append(_read_attachment_text(record.uuid, name))
            except Exception as exc:
                parts.append(f"[failed to read {name}: {exc}]")
            parts.append("")
    else:
        parts.append("=== attachments ===")
        parts.append("(none)")

    return "\n".join(parts), record.uuid


def parse_decision_type(content: str) -> int:
    match = _JSON_LINE.search(content or "")
    if not match:
        raise ValueError("decision JSON not found in agent output")
    payload = json.loads(match.group(0))
    value = int(payload.get("decision_type"))
    if value not in VALID_DECISION_TYPES:
        raise ValueError(f"invalid decision_type from agent: {value}")
    if value == DECISION_TYPE_PENDING:
        # Empty/unusable → treat as non-job unless content truly pending; map to non-job
        # only when agent chose 0 for empty — keep 0 allowed but prefer callers to set 5/10/11.
        return DECISION_TYPE_PENDING
    return value


class JobDecisionAgentService:
    """In-process LangGraph agent without MCP (mail text is injected in the user message)."""

    def __init__(self) -> None:
        self._agent: Any | None = None
        self._runtime_mode: str = "mock"

    @property
    def agent_id(self) -> str:
        return STATIC_CONFIG.agent_id

    @property
    def is_ready(self) -> bool:
        return self._agent is not None

    async def initialize(self, runtime_mode: str | None = None) -> None:
        mode = normalize_runtime_mode(runtime_mode or resolve_agent_runtime_mode())
        self._runtime_mode = mode
        llm = _build_llm(mode)
        prompt = build_system_prompt()
        self._agent = create_react_agent(
            model=llm,
            tools=[],
            prompt=SystemMessage(content=prompt),
        )
        logger.info(
            "JOB_DECISION_AGENT initialized mode=%s llm=%s",
            mode,
            STATIC_CONFIG.http_llm_model if mode == "http" else "control-plane",
        )

    async def invoke(self, message: str) -> AgentInvokeResult:
        if self._agent is None:
            await self.initialize()
        assert self._agent is not None
        return await invoke_agent(
            self._agent,
            message,
            None,
            agent_id=STATIC_CONFIG.agent_id,
            agent_name=STATIC_CONFIG.agent_name,
            mcp_server_keys=[],
        )

    async def evaluate_received_mail(
        self,
        database_path,
        mail_uuid: str,
        *,
        persist: bool = True,
    ) -> dict[str, Any]:
        message, uuid_value = build_mail_decision_message(database_path, mail_uuid)
        result = await self.invoke(message)
        decision_type = parse_decision_type(result.content)
        if decision_type == DECISION_TYPE_PENDING:
            # Empty mail → insufficient/non-actionable; use 11 if no content signals job intent.
            decision_type = DECISION_TYPE_NON_JOB

        record = None
        if persist:
            record = update_decision_type(database_path, uuid_value, decision_type)

        return {
            "uuid": uuid_value,
            "decision_type": decision_type,
            "persisted": persist,
            "content": result.content,
            "tools_used": [
                {"name": tool.name, "mcp_server": tool.mcp_server} for tool in result.tools_used
            ],
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "record": (
                {
                    "idx": record.idx,
                    "decision_type": record.decision_type,
                }
                if record is not None
                else None
            ),
        }

    def status(self) -> dict[str, Any]:
        return {
            "agent_id": STATIC_CONFIG.agent_id,
            "agent_name": STATIC_CONFIG.agent_name,
            "ready": self.is_ready,
            "runtime_mode": self._runtime_mode,
            "decision_types": {
                "pending": DECISION_TYPE_PENDING,
                "insufficient": DECISION_TYPE_INSUFFICIENT,
                "job": DECISION_TYPE_JOB,
                "non_job": DECISION_TYPE_NON_JOB,
            },
            "llm": (
                {
                    "base_url": STATIC_CONFIG.http_llm_base_url,
                    "model": STATIC_CONFIG.http_llm_model,
                }
                if self._runtime_mode == "http"
                else {"source": "control-plane-existing-llm"}
            ),
        }


job_decision_agent_service = JobDecisionAgentService()
