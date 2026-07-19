"""Helpdesk system agent: route user queries to regular/inventory agents unchanged."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from backend.app.agents.base import AgentDefinition, AgentInvokeResult, ToolUsage, extract_token_usage_from_text
from backend.app.agents.system_agents import HELPDESK_AGENT
from backend.app.llm.factory import get_llm
from backend.app.logging.prompt_debug import (
    estimate_tokens,
    prompt_debug_scope,
    record_orchestration,
    wrap_llm_for_prompt_debug,
)

logger = logging.getLogger(__name__)

ROUTING_SYSTEM_PROMPT = (
    "You are a help desk system agent. You can select agents from the provided catalog "
    "to answer user questions; however, to avoid overcomplicating the thought process, "
    "you are limited to using three agents at a time. "
    "Respond with valid JSON only (no markdown) with keys: "
    "agent_id (string), agent_name (string), rationale (string). "
    "Use only agent_id values from the catalog. "
    "If the inquiry does not concern infrastructure topics such as Kubernetes, VMware, "
    "KubeVirt, or Ansible, a direct, general response will be provided: "
    "set agent_id and agent_name to empty strings and put the direct answer in rationale."
)


@dataclass(frozen=True)
class HelpdeskRouteDecision:
    agent_id: str
    agent_name: str
    rationale: str
    is_direct: bool = False
    direct_answer: str = ""


def _extract_json_block(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

    match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _callable_agent_catalog(agent_manager: Any) -> list[AgentDefinition]:
    """Regular agents including inventory; exclude system agents and helpdesk itself."""
    catalog: list[AgentDefinition] = []
    for definition in getattr(agent_manager, "agent_definitions", []) or []:
        if definition.agent_id == HELPDESK_AGENT.agent_id:
            continue
        catalog.append(definition)
    return catalog


def decorate_helpdesk_response(content: str) -> str:
    """Apply presentation-only decoration; never change factual substance."""
    stripped = content.strip()
    if not stripped or stripped.startswith("```"):
        return content

    if (stripped.startswith("{") and stripped.endswith("}")) or (
        stripped.startswith("[") and stripped.endswith("]")
    ):
        try:
            parsed = json.loads(stripped)
            pretty = json.dumps(parsed, ensure_ascii=False, indent=2)
            return f"```json\n{pretty}\n```"
        except json.JSONDecodeError:
            pass

    return content


async def _select_agent(
    agent_manager: Any,
    message: str,
    catalog: list[AgentDefinition],
) -> HelpdeskRouteDecision:
    catalog_payload = [
        {
            "agent_id": agent.agent_id,
            "name": agent.name,
            "role": agent.role,
            "mcp_servers": agent.mcp_server_keys,
        }
        for agent in catalog
    ]
    prompt = (
        f"User question:\n{message}\n\n"
        f"Available agents:\n{json.dumps(catalog_payload, ensure_ascii=False)}"
    )

    record_orchestration(
        agent_id=HELPDESK_AGENT.agent_id,
        agent_name=HELPDESK_AGENT.name,
        event="helpdesk_route_start",
        detail=f"catalog_size={len(catalog)}\nquestion_chars={len(message)}",
        input_tokens=estimate_tokens(prompt),
    )

    with prompt_debug_scope(
        caller_agent_id=HELPDESK_AGENT.agent_id,
        caller_agent_name=HELPDESK_AGENT.name,
    ):
        llm = wrap_llm_for_prompt_debug(
            get_llm(),
            agent_id=HELPDESK_AGENT.agent_id,
            agent_name=HELPDESK_AGENT.name,
        )
        response = await llm.ainvoke(
            [
                SystemMessage(content=ROUTING_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
        )

    content = response.content if isinstance(response.content, str) else str(response.content)
    parsed = _extract_json_block(content) or {}
    agent_id = str(parsed.get("agent_id") or "").strip()
    agent_name = str(parsed.get("agent_name") or "").strip()
    rationale = str(parsed.get("rationale") or "").strip()
    direct_answer = str(parsed.get("answer") or "").strip()

    # Non-infra / general inquiry: empty or sentinel agent_id → answer directly.
    is_direct_marker = agent_id.lower() in {"", "none", "null", "direct", "general", "n/a"}
    if is_direct_marker:
        answer = direct_answer or rationale
        if answer:
            decision = HelpdeskRouteDecision(
                agent_id="",
                agent_name="",
                rationale=rationale,
                is_direct=True,
                direct_answer=answer,
            )
            record_orchestration(
                agent_id=HELPDESK_AGENT.agent_id,
                agent_name=HELPDESK_AGENT.name,
                event="helpdesk_route_direct",
                detail=f"direct_response chars={len(answer)}\nrationale={rationale}",
                response=json.dumps(
                    {"agent_id": "", "agent_name": "", "rationale": rationale},
                    ensure_ascii=False,
                ),
                output_tokens=estimate_tokens(content),
            )
            return decision

    allowed = {agent.agent_id: agent for agent in catalog}
    if agent_id not in allowed:
        # Lightweight keyword fallback before failing.
        lowered = message.lower()
        for candidate in catalog:
            blob = f"{candidate.agent_id} {candidate.name} {candidate.role}".lower()
            if any(token and token in blob for token in lowered.replace(",", " ").split() if len(token) > 2):
                agent_id = candidate.agent_id
                agent_name = candidate.name
                rationale = rationale or "fallback keyword match"
                break

    if agent_id not in allowed:
        preferred = next((agent for agent in catalog if "inventory" in agent.agent_id), catalog[0])
        agent_id = preferred.agent_id
        agent_name = preferred.name
        rationale = rationale or "fallback default agent"

    if not agent_name:
        agent_name = allowed[agent_id].name

    decision = HelpdeskRouteDecision(
        agent_id=agent_id,
        agent_name=agent_name,
        rationale=rationale,
    )
    record_orchestration(
        agent_id=HELPDESK_AGENT.agent_id,
        agent_name=HELPDESK_AGENT.name,
        event="helpdesk_route_selected",
        detail=f"selected={agent_id} ({agent_name})\nrationale={rationale}",
        response=json.dumps(
            {"agent_id": agent_id, "agent_name": agent_name, "rationale": rationale},
            ensure_ascii=False,
        ),
        output_tokens=estimate_tokens(content),
    )
    return decision


async def handle_helpdesk_query(agent_manager: Any, message: str) -> AgentInvokeResult:
    """Route the user message to one regular/inventory agent, or answer general inquiries directly."""
    from backend.app.services.agent_invocation import AgentInvocationError, invoke_agent_by_id

    catalog = _callable_agent_catalog(agent_manager)
    if not catalog:
        content = "호출 가능한 일반 에이전트가 없습니다. 관리자에게 문의해 주세요."
        input_tokens, output_tokens = extract_token_usage_from_text(message, content)
        return AgentInvokeResult(
            content=content,
            tools_used=[],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    try:
        decision = await _select_agent(agent_manager, message, catalog)
    except Exception as exc:
        logger.exception("Helpdesk routing failed")
        content = f"헬프데스크 에이전트 선택에 실패했습니다: {exc}"
        input_tokens, output_tokens = extract_token_usage_from_text(message, content)
        return AgentInvokeResult(
            content=content,
            tools_used=[],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    if decision.is_direct:
        decorated = decorate_helpdesk_response(decision.direct_answer)
        input_tokens, output_tokens = extract_token_usage_from_text(message, decorated)
        record_orchestration(
            agent_id=HELPDESK_AGENT.agent_id,
            agent_name=HELPDESK_AGENT.name,
            event="helpdesk_direct_complete",
            detail=f"rationale={decision.rationale} decorated={decorated != decision.direct_answer}",
            response=decorated[:2000],
            output_tokens=output_tokens,
        )
        return AgentInvokeResult(
            content=decorated,
            tools_used=[ToolUsage(name="direct:general", mcp_server="helpdesk")],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    target_id = decision.agent_id
    target_name = decision.agent_name
    rationale = decision.rationale

    if hasattr(agent_manager, "mark_agent_working"):
        agent_manager.mark_agent_working(target_id, f"헬프데스크→{target_name}")

    try:
        with prompt_debug_scope(
            caller_agent_id=HELPDESK_AGENT.agent_id,
            caller_agent_name=HELPDESK_AGENT.name,
        ):
            # Forward the original user message unchanged — no rewrite/retry loop.
            result = await invoke_agent_by_id(
                agent_manager,
                target_id,
                message,
                caller_agent_id=HELPDESK_AGENT.agent_id,
            )
    except AgentInvocationError as exc:
        if hasattr(agent_manager, "mark_agent_error"):
            agent_manager.mark_agent_error(target_id, str(exc), input_message=message)
        content = f"[{target_name}] 호출에 실패했습니다: {exc}"
        input_tokens, output_tokens = extract_token_usage_from_text(message, content)
        return AgentInvokeResult(
            content=content,
            tools_used=[ToolUsage(name=f"route:{target_id}", mcp_server="helpdesk")],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    except Exception as exc:
        if hasattr(agent_manager, "mark_agent_error"):
            agent_manager.mark_agent_error(target_id, str(exc), input_message=message)
        raise
    finally:
        if hasattr(agent_manager, "mark_agent_idle"):
            agent_manager.mark_agent_idle(target_id)

    decorated = decorate_helpdesk_response(result.content)
    tools = list(result.tools_used)
    tools.insert(0, ToolUsage(name=f"route:{target_id}", mcp_server="helpdesk"))

    record_orchestration(
        agent_id=HELPDESK_AGENT.agent_id,
        agent_name=HELPDESK_AGENT.name,
        event="helpdesk_forward_complete",
        detail=f"target={target_id} rationale={rationale} decorated={decorated != result.content}",
        response=decorated[:2000],
        output_tokens=result.output_tokens,
    )

    return AgentInvokeResult(
        content=decorated,
        tools_used=tools,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
