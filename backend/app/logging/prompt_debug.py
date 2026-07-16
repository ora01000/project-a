"""In-memory capture of LLM prompts and system-agent orchestration for admin debugging."""

from __future__ import annotations

import logging
import threading
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterator, Literal
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult, LLMResult

logger = logging.getLogger(__name__)

EntryKind = Literal["llm", "orchestration"]

_MAX_ENTRIES = 500
_lock = threading.Lock()
_next_idx = 1
_entries: deque[dict[str, Any]] = deque(maxlen=_MAX_ENTRIES)
_WRAPPED_ATTR = "_prompt_debug_wrapped"

_prompt_debug_context: ContextVar[dict[str, Any] | None] = ContextVar(
    "prompt_debug_context",
    default=None,
)


def _estimate_tokens(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    return max(1, len(stripped) // 4)


def estimate_tokens(text: str) -> int:
    return _estimate_tokens(text)


def _extract_message_content(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = [part.get("text", "") for part in content if isinstance(part, dict)]
        return "".join(text_parts) or str(content)
    return str(content)


def get_prompt_debug_context() -> dict[str, Any]:
    return dict(_prompt_debug_context.get() or {})


@contextmanager
def prompt_debug_scope(
    *,
    job_idx: int | None = None,
    caller_agent_id: str | None = None,
    caller_agent_name: str | None = None,
    step_index: int | None = None,
) -> Iterator[None]:
    """Attach job/caller metadata to subsequent LLM / orchestration records."""
    current = get_prompt_debug_context()
    next_ctx = {**current}
    if job_idx is not None:
        next_ctx["job_idx"] = job_idx
    if caller_agent_id:
        next_ctx["caller_agent_id"] = caller_agent_id
    if caller_agent_name:
        next_ctx["caller_agent_name"] = caller_agent_name
    if step_index is not None:
        next_ctx["step_index"] = step_index
    token = _prompt_debug_context.set(next_ctx)
    try:
        yield
    finally:
        _prompt_debug_context.reset(token)


@dataclass(frozen=True)
class PromptDebugEntry:
    idx: int
    timestamp: str
    kind: EntryKind
    agent_id: str
    agent_name: str
    prompt: str
    response: str
    input_tokens: int
    output_tokens: int
    job_idx: int | None = None
    caller_agent_id: str | None = None
    caller_agent_name: str | None = None
    step_index: int | None = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "idx": self.idx,
            "timestamp": self.timestamp,
            "kind": self.kind,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "prompt": self.prompt,
            "response": self.response,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "job_idx": self.job_idx,
            "caller_agent_id": self.caller_agent_id,
            "caller_agent_name": self.caller_agent_name,
            "step_index": self.step_index,
        }


def _message_role(message: Any) -> str:
    name = type(message).__name__
    if name.endswith("Message"):
        return name[: -len("Message")].lower() or "message"
    return name.lower()


def format_messages_as_prompt(messages: list[Any]) -> str:
    parts: list[str] = []
    for message in messages:
        role = _message_role(message)
        content = _extract_message_content(message).strip()
        tool_calls = getattr(message, "tool_calls", None) or []
        if tool_calls:
            call_lines = []
            for tool_call in tool_calls:
                if isinstance(tool_call, dict):
                    name = tool_call.get("name", "tool")
                    args = tool_call.get("args", {})
                else:
                    name = getattr(tool_call, "name", "tool")
                    args = getattr(tool_call, "args", {})
                call_lines.append(f"{name}({args})")
            tool_text = "\n".join(call_lines)
            content = f"{content}\n[tool_calls]\n{tool_text}".strip() if content else f"[tool_calls]\n{tool_text}"
        parts.append(f"[{role}]\n{content}")
    return "\n\n".join(parts).strip()


def format_ai_message_as_response(message: Any) -> str:
    content = _extract_message_content(message).strip()
    tool_calls = getattr(message, "tool_calls", None) or []
    if not tool_calls:
        return content
    call_lines = []
    for tool_call in tool_calls:
        if isinstance(tool_call, dict):
            name = tool_call.get("name", "tool")
            args = tool_call.get("args", {})
        else:
            name = getattr(tool_call, "name", "tool")
            args = getattr(tool_call, "args", {})
        call_lines.append(f"{name}({args})")
    tool_text = "\n".join(call_lines)
    if content:
        return f"{content}\n\n[tool_calls]\n{tool_text}"
    return f"[tool_calls]\n{tool_text}"


def _response_text_from_chat_result(result: ChatResult) -> str:
    generations = result.generations or []
    if not generations:
        return ""
    message = getattr(generations[0], "message", None)
    if message is not None:
        return format_ai_message_as_response(message)
    text = getattr(generations[0], "text", None)
    return str(text).strip() if text else ""


def _response_text_from_llm_result(response: LLMResult) -> str:
    generations = response.generations or []
    if not generations or not generations[0]:
        return ""
    generation = generations[0][0]
    message = getattr(generation, "message", None)
    if message is not None:
        return format_ai_message_as_response(message)
    text = getattr(generation, "text", None)
    return str(text).strip() if text else ""


def _usage_from_message_metadata(message: Any) -> tuple[int, int]:
    metadata = getattr(message, "response_metadata", None) or {}
    if not isinstance(metadata, dict):
        return 0, 0
    usage = metadata.get("token_usage") or metadata.get("usage") or {}
    if not isinstance(usage, dict):
        return 0, 0
    input_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
    output_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
    if input_tokens is None and output_tokens is None:
        return 0, 0
    return int(input_tokens or 0), int(output_tokens or 0)


def _usage_from_chat_result(result: ChatResult) -> tuple[int, int]:
    llm_output = result.llm_output if isinstance(result.llm_output, dict) else {}
    token_usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
    if isinstance(token_usage, dict):
        input_tokens = token_usage.get("prompt_tokens", token_usage.get("input_tokens"))
        output_tokens = token_usage.get("completion_tokens", token_usage.get("output_tokens"))
        if input_tokens is not None or output_tokens is not None:
            return int(input_tokens or 0), int(output_tokens or 0)

    generations = result.generations or []
    if generations:
        return _usage_from_message_metadata(getattr(generations[0], "message", None))
    return 0, 0


def _usage_from_llm_result(response: LLMResult) -> tuple[int, int]:
    llm_output = response.llm_output if isinstance(response.llm_output, dict) else {}
    token_usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
    if isinstance(token_usage, dict):
        input_tokens = token_usage.get("prompt_tokens", token_usage.get("input_tokens"))
        output_tokens = token_usage.get("completion_tokens", token_usage.get("output_tokens"))
        if input_tokens is not None or output_tokens is not None:
            return int(input_tokens or 0), int(output_tokens or 0)

    generations = response.generations or []
    if generations and generations[0]:
        generation = generations[0][0]
        message = getattr(generation, "message", None)
        usage = _usage_from_message_metadata(message)
        if usage != (0, 0):
            return usage
        content = _extract_message_content(message) if message is not None else str(generation)
        return 0, _estimate_tokens(content)
    return 0, 0


def _context_fields() -> dict[str, Any]:
    ctx = get_prompt_debug_context()
    return {
        "job_idx": ctx.get("job_idx"),
        "caller_agent_id": ctx.get("caller_agent_id"),
        "caller_agent_name": ctx.get("caller_agent_name"),
        "step_index": ctx.get("step_index"),
    }


def record_prompt_debug(
    *,
    agent_id: str,
    agent_name: str,
    prompt: str,
    response: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    kind: EntryKind = "llm",
    job_idx: int | None = None,
    caller_agent_id: str | None = None,
    caller_agent_name: str | None = None,
    step_index: int | None = None,
) -> PromptDebugEntry:
    global _next_idx
    ctx = _context_fields()
    with _lock:
        idx = _next_idx
        _next_idx += 1
        entry = PromptDebugEntry(
            idx=idx,
            timestamp=datetime.now(UTC).astimezone().isoformat(timespec="seconds"),
            kind=kind,
            agent_id=agent_id.strip() or "unknown",
            agent_name=agent_name.strip() or agent_id,
            prompt=prompt,
            response=response,
            input_tokens=max(0, int(input_tokens)),
            output_tokens=max(0, int(output_tokens)),
            job_idx=job_idx if job_idx is not None else ctx.get("job_idx"),
            caller_agent_id=caller_agent_id or ctx.get("caller_agent_id"),
            caller_agent_name=caller_agent_name or ctx.get("caller_agent_name"),
            step_index=step_index if step_index is not None else ctx.get("step_index"),
        )
        _entries.append(entry.to_dict())
        return entry


def record_orchestration(
    *,
    agent_id: str,
    agent_name: str,
    event: str,
    detail: str = "",
    response: str = "",
    job_idx: int | None = None,
    step_index: int | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> PromptDebugEntry:
    prompt = f"[orchestration]\n{event}"
    if detail.strip():
        prompt = f"{prompt}\n\n{detail.strip()}"
    return record_prompt_debug(
        agent_id=agent_id,
        agent_name=agent_name,
        prompt=prompt,
        response=response,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        kind="orchestration",
        job_idx=job_idx,
        step_index=step_index,
    )


def list_prompt_debug_entries(limit: int | None = 500) -> list[dict[str, Any]]:
    with _lock:
        items = list(_entries)
    items.reverse()
    if limit is None:
        return items
    return items[: max(1, limit)]


def clear_prompt_debug_entries() -> int:
    with _lock:
        count = len(_entries)
        _entries.clear()
        return count


def _finalize_usage(prompt: str, response: str, input_tokens: int, output_tokens: int) -> tuple[int, int]:
    if input_tokens <= 0:
        input_tokens = _estimate_tokens(prompt)
    if output_tokens <= 0 and response:
        output_tokens = _estimate_tokens(response)
    return input_tokens, output_tokens


def record_llm_exchange(
    *,
    agent_id: str,
    agent_name: str,
    messages: list[Any],
    response_text: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> PromptDebugEntry | None:
    prompt = format_messages_as_prompt(list(messages))
    if not prompt and not response_text:
        return None
    input_tokens, output_tokens = _finalize_usage(prompt, response_text, input_tokens, output_tokens)
    return record_prompt_debug(
        agent_id=agent_id,
        agent_name=agent_name,
        prompt=prompt,
        response=response_text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        kind="llm",
    )


def wrap_llm_for_prompt_debug(llm: BaseChatModel, *, agent_id: str, agent_name: str) -> BaseChatModel:
    """Wrap ChatModel generate methods so capture survives LangGraph bind_tools."""
    if getattr(llm, _WRAPPED_ATTR, False):
        return llm

    original_generate = llm._generate
    original_agenerate = llm._agenerate

    def _record(messages: list[BaseMessage], result: ChatResult) -> None:
        try:
            response_text = _response_text_from_chat_result(result)
            input_tokens, output_tokens = _usage_from_chat_result(result)
            record_llm_exchange(
                agent_id=agent_id,
                agent_name=agent_name,
                messages=list(messages),
                response_text=response_text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        except Exception:
            logger.exception("Failed to record prompt debug for agent %s", agent_id)

    def _generate(messages: list[BaseMessage], *args: Any, **kwargs: Any) -> ChatResult:
        result = original_generate(messages, *args, **kwargs)
        _record(messages, result)
        return result

    async def _agenerate(messages: list[BaseMessage], *args: Any, **kwargs: Any) -> ChatResult:
        result = await original_agenerate(messages, *args, **kwargs)
        _record(messages, result)
        return result

    object.__setattr__(llm, "_generate", _generate)
    object.__setattr__(llm, "_agenerate", _agenerate)
    object.__setattr__(llm, _WRAPPED_ATTR, True)
    return llm


class PromptDebugCallback(BaseCallbackHandler):
    """Capture every chat-model call for an agent (invoke-config path)."""

    def __init__(self, *, agent_id: str, agent_name: str) -> None:
        self.agent_id = agent_id
        self.agent_name = agent_name
        self._pending_prompts: dict[str, str] = {}

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        flat = messages[0] if messages else []
        prompt = format_messages_as_prompt(list(flat))
        self._pending_prompts[str(run_id)] = prompt

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        prompt = self._pending_prompts.pop(str(run_id), "")
        if not prompt:
            return
        response_text = _response_text_from_llm_result(response)
        input_tokens, output_tokens = _usage_from_llm_result(response)
        input_tokens, output_tokens = _finalize_usage(prompt, response_text, input_tokens, output_tokens)
        record_prompt_debug(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            prompt=prompt,
            response=response_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            kind="llm",
        )

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._pending_prompts.pop(str(run_id), None)
