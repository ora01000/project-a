"""Standalone JOB_DECISION_AGENT — static LangGraph agent (no AXIT / mock catalog)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from backend.app.agents.base import AgentInvokeResult, invoke_agent
from backend.app.config import _env_setting, resolve_agent_runtime_mode
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


@dataclass(frozen=True)
class ParsedDecision:
    decision_type: int
    infra: str = "unknown"
    job_kind: str = "none"
    missing: list[str] = field(default_factory=list)
    summary: str = ""
    reply_ko: str = ""
    operator_ko: str = ""


def parse_decision_payload(content: str) -> ParsedDecision:
    text = content or ""
    decoder = json.JSONDecoder()
    payload: dict[str, Any] | None = None
    tail = ""
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and "decision_type" in parsed:
            payload = parsed
            tail = text[index + end :].strip()
            break
    if payload is None:
        raise ValueError("decision JSON not found in agent output")

    value = int(payload.get("decision_type"))
    if value not in VALID_DECISION_TYPES:
        raise ValueError(f"invalid decision_type from agent: {value}")

    missing_raw = payload.get("missing") or []
    missing = [str(item).strip() for item in missing_raw if str(item).strip()] if isinstance(missing_raw, list) else []
    return ParsedDecision(
        decision_type=value,
        infra=str(payload.get("infra") or "unknown").strip() or "unknown",
        job_kind=str(payload.get("job_kind") or "none").strip() or "none",
        missing=missing,
        summary=str(payload.get("summary") or "").strip(),
        reply_ko=str(payload.get("reply_ko") or "").strip(),
        operator_ko=tail,
    )


def parse_decision_type(content: str) -> int:
    return parse_decision_payload(content).decision_type


def _build_llm(runtime_mode: str) -> ChatOpenAI:
    from backend.app.logging.prompt_debug import wrap_llm_for_prompt_debug

    if runtime_mode == "http":
        api_key = _env_setting(STATIC_CONFIG.http_llm_api_key_env)
        if not api_key:
            raise RuntimeError(
                f"http 모드 JOB_DECISION_AGENT 는 {STATIC_CONFIG.http_llm_api_key_env} 가 필요합니다."
            )
        llm: ChatOpenAI = ChatOpenAI(
            base_url=STATIC_CONFIG.http_llm_base_url,
            api_key=api_key,
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
        parts.append("=== attachments (text) ===")
        parts.append("(none)")

    if record.unreadable_attachment_names:
        parts.append("=== unreadable attachments (office/binary; treat as insufficient for type 10) ===")
        for name in record.unreadable_attachment_names:
            parts.append(f"- {name}")
        parts.append("")

    return "\n".join(parts), record.uuid


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
        parsed = parse_decision_payload(result.content)
        decision_type = parsed.decision_type
        if decision_type == DECISION_TYPE_PENDING:
            decision_type = DECISION_TYPE_NON_JOB

        record = None
        if persist:
            record = update_decision_type(database_path, uuid_value, decision_type)

        return {
            "uuid": uuid_value,
            "decision_type": decision_type,
            "parsed": parsed,
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
