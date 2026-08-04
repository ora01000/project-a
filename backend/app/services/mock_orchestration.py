"""Mock platform orchestrator agents: route to infra agents without MCP tools."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage

from backend.app.agents.base import AgentDefinition, AgentInvokeResult, ToolUsage, extract_token_usage_from_text
from backend.app.agents.mock_platform_agents import (
    MockPlatformAgentSpec,
    get_mock_platform_agent_spec,
    resolve_callable_catalog_agent_ids,
)
from backend.app.llm.factory import get_llm
from backend.app.logging.prompt_debug import (
    estimate_tokens,
    prompt_debug_scope,
    record_orchestration,
    wrap_llm_for_prompt_debug,
)

logger = logging.getLogger(__name__)

_ROUTING_JSON_INSTRUCTION = (
    "Respond with valid JSON only (no markdown) with keys: "
    "agent_id (string), agent_name (string), rationale (string). "
    "Use only agent_id values from the provided catalog when delegating. "
    "If you can answer directly without delegating, set agent_id and agent_name to empty strings "
    "and put the full answer in rationale."
)


@dataclass(frozen=True)
class OrchestrationRouteDecision:
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


def _build_routing_system_prompt(spec: MockPlatformAgentSpec) -> str:
    return f"{spec.system_prompt.strip()}\n\n{_ROUTING_JSON_INSTRUCTION}"


def _callable_catalog(
    agent_manager: Any,
    spec: MockPlatformAgentSpec,
) -> list[AgentDefinition]:
    available_ids = set(getattr(agent_manager, "agents", {}).keys())
    catalog: list[AgentDefinition] = []
    for agent_id in resolve_callable_catalog_agent_ids(spec, available_agent_ids=available_ids):
        try:
            catalog.append(agent_manager.get_definition(agent_id))
        except KeyError:
            continue
    return catalog


async def _select_delegate_agent(
    spec: MockPlatformAgentSpec,
    message: str,
    catalog: list[AgentDefinition],
) -> OrchestrationRouteDecision:
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
        agent_id=spec.agent_id,
        agent_name=spec.agent_name,
        event="mock_orchestrator_route_start",
        detail=f"catalog_size={len(catalog)}\nquestion_chars={len(message)}",
        input_tokens=estimate_tokens(prompt),
    )

    with prompt_debug_scope(
        caller_agent_id=spec.agent_id,
        caller_agent_name=spec.agent_name,
    ):
        llm = wrap_llm_for_prompt_debug(
            get_llm(),
            agent_id=spec.agent_id,
            agent_name=spec.agent_name,
        )
        response = await llm.ainvoke(
            [
                SystemMessage(content=_build_routing_system_prompt(spec)),
                HumanMessage(content=prompt),
            ],
        )

    content = response.content if isinstance(response.content, str) else str(response.content)
    parsed = _extract_json_block(content) or {}
    agent_id = str(parsed.get("agent_id") or "").strip()
    agent_name = str(parsed.get("agent_name") or "").strip()
    rationale = str(parsed.get("rationale") or "").strip()

    is_direct_marker = agent_id.lower() in {"", "none", "null", "direct", "general", "n/a"}
    if is_direct_marker and rationale:
        return OrchestrationRouteDecision(
            agent_id="",
            agent_name="",
            rationale=rationale,
            is_direct=True,
            direct_answer=rationale,
        )

    allowed = {agent.agent_id: agent for agent in catalog}
    if agent_id not in allowed and catalog:
        preferred = catalog[0]
        agent_id = preferred.agent_id
        agent_name = preferred.name
        rationale = rationale or "fallback default agent"

    if agent_id and not agent_name and agent_id in allowed:
        agent_name = allowed[agent_id].name

    return OrchestrationRouteDecision(
        agent_id=agent_id,
        agent_name=agent_name,
        rationale=rationale,
    )


async def handle_mock_orchestration_query(
    agent_manager: Any,
    agent_id: str,
    message: str,
    *,
    agent_runtime: Any | None = None,
) -> AgentInvokeResult:
    from backend.app.services.agent_invocation import AgentInvocationError, invoke_agent_by_id

    spec = get_mock_platform_agent_spec(agent_id)
    if spec is None:
        raise AgentInvocationError(f"Unknown mock orchestrator agent '{agent_id}'")

    catalog = _callable_catalog(agent_manager, spec)
    if not catalog:
        content = "호출 가능한 인프라 에이전트가 없습니다. 관리자에게 문의해 주세요."
        input_tokens, output_tokens = extract_token_usage_from_text(message, content)
        return AgentInvokeResult(
            content=content,
            tools_used=[],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    try:
        decision = await _select_delegate_agent(spec, message, catalog)
    except Exception as exc:
        logger.exception("Mock orchestrator routing failed for %s", agent_id)
        content = f"[{spec.agent_name}] 에이전트 선택에 실패했습니다: {exc}"
        input_tokens, output_tokens = extract_token_usage_from_text(message, content)
        return AgentInvokeResult(
            content=content,
            tools_used=[],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    if decision.is_direct:
        input_tokens, output_tokens = extract_token_usage_from_text(message, decision.direct_answer)
        record_orchestration(
            agent_id=spec.agent_id,
            agent_name=spec.agent_name,
            event="mock_orchestrator_direct_complete",
            detail=decision.rationale[:500],
            response=decision.direct_answer[:2000],
            output_tokens=output_tokens,
        )
        return AgentInvokeResult(
            content=decision.direct_answer,
            tools_used=[ToolUsage(name="direct:orchestrator", mcp_server=spec.agent_id)],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    target_id = decision.agent_id
    target_name = decision.agent_name

    route_task_id: str | None = None
    if hasattr(agent_manager, "mark_agent_working"):
        route_task_id = agent_manager.mark_agent_working(
            target_id,
            f"{spec.agent_name}→{target_name}",
            task_id=uuid4().hex,
        )

    try:
        with prompt_debug_scope(
            caller_agent_id=spec.agent_id,
            caller_agent_name=spec.agent_name,
        ):
            if agent_runtime is not None:
                from backend.app.services.agent_runtime_client import AgentInvokeRequest

                result = await agent_runtime.invoke(
                    AgentInvokeRequest(
                        agent_id=target_id,
                        message=message,
                        caller_agent_id=spec.agent_id,
                    ),
                )
            else:
                result = await invoke_agent_by_id(
                    agent_manager,
                    target_id,
                    message,
                    caller_agent_id=spec.agent_id,
                    agent_runtime=agent_runtime,
                )
    except AgentInvocationError as exc:
        if hasattr(agent_manager, "mark_agent_error"):
            agent_manager.mark_agent_error(target_id, str(exc), input_message=message)
        content = f"[{target_name}] 호출에 실패했습니다: {exc}"
        input_tokens, output_tokens = extract_token_usage_from_text(message, content)
        return AgentInvokeResult(
            content=content,
            tools_used=[ToolUsage(name=f"route:{target_id}", mcp_server=spec.agent_id)],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    finally:
        if hasattr(agent_manager, "mark_agent_idle") and route_task_id is not None:
            agent_manager.mark_agent_idle(target_id, route_task_id)

    tools = list(result.tools_used)
    tools.insert(0, ToolUsage(name=f"route:{target_id}", mcp_server=spec.agent_id))
    record_orchestration(
        agent_id=spec.agent_id,
        agent_name=spec.agent_name,
        event="mock_orchestrator_forward_complete",
        detail=f"target={target_id} rationale={decision.rationale}",
        response=result.content[:2000],
        output_tokens=result.output_tokens,
    )
    return AgentInvokeResult(
        content=result.content,
        tools_used=tools,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
