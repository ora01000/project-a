import json
import logging
import re
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from backend.app.agents.base import AgentDefinition
from backend.app.agents.inventory_tool import INVENTORY_AGENT_ID, QUERY_INVENTORY_TOOL_NAME
from backend.app.agents.registry import load_agent_definitions
from backend.app.agents.system_agents import JOB_PLANNING_AGENT, NotifyChannel
from backend.app.db.jobs import (
    JOB_STATE_PLAN_COMPLETED,
    JOB_STATE_RECEIVED,
    Job,
    create_job,
    update_job_plan,
)
from backend.app.db.notifications import NOTIFICATION_TYPE_REVIEW_REQUEST
from backend.app.llm.factory import get_llm
from backend.app.logging.prompt_debug import (
    estimate_tokens,
    prompt_debug_scope,
    record_orchestration,
    wrap_llm_for_prompt_debug,
)
from backend.app.services.job_notifications import send_job_notifications

logger = logging.getLogger(__name__)

PLAN_DESCRIPTION_MAX_CHARS = 200

PLANNING_SYSTEM_PROMPT = (
    "You are the Job Planning system agent. Analyze the job request and produce an execution plan "
    "as JSON only. The JSON must have keys: summary (string), steps (array). "
    "Each step must include ONLY: agent_id, agent_name, description. "
    "Do NOT choose tools or tool_params — tooling is decided later by consulting each selected agent. "
    "Use only agent_id values from the provided agent catalog. "
    f"Keep each step.description under {PLAN_DESCRIPTION_MAX_CHARS} characters — "
    "only the minimal instruction for that agent. "
    "Respond with valid JSON only, no markdown."
)

TOOL_CONSULT_SYSTEM_PROMPT = (
    "You are being consulted during job planning. "
    "Based on your role and the available tools listed below, recommend which tool to use "
    "for the assigned step. Do NOT execute tools. "
    "Respond with valid JSON only (no markdown) with keys: "
    "tool_name (string), tool_params (object), rationale (string). "
    "Pick exactly one primary tool_name from the available tools list. "
    "If no suitable tool exists, set tool_name to \"agent_invoke\" and tool_params to "
    '{{"message": "<short task summary>"}}.'
)


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


def _truncate(text: str, max_chars: int) -> str:
    stripped = text.strip()
    if len(stripped) <= max_chars:
        return stripped
    return stripped[: max_chars - 1].rstrip() + "…"


def _normalize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    steps = plan.get("steps")
    if not isinstance(steps, list):
        return plan
    normalized_steps: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        item = dict(step)
        description = str(item.get("description") or "")
        item["description"] = _truncate(description, PLAN_DESCRIPTION_MAX_CHARS)
        if "tool_name" not in item:
            item["tool_name"] = ""
        if not isinstance(item.get("tool_params"), dict):
            item["tool_params"] = {}
        normalized_steps.append(item)
    return {**plan, "steps": normalized_steps}


def _plan_summary_detail(plan: dict[str, Any], *, source: str) -> str:
    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    lines = [
        f"source={source}",
        f"summary={plan.get('summary', '')}",
        f"steps={len(steps)}",
    ]
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue
        description = str(step.get("description") or "")
        lines.append(
            f"step {index}: agent={step.get('agent_id')} "
            f"tool={step.get('tool_name') or '-'} "
            f"desc_chars={len(description)} ~tokens={estimate_tokens(description)}"
        )
    return "\n".join(lines)


def _build_fallback_plan(job: Job, agents: list[AgentDefinition]) -> dict[str, Any]:
    preferred = next((agent for agent in agents if "k8s" in agent.agent_id), agents[0] if agents else None)
    if preferred is None:
        return {
            "summary": "등록된 에이전트가 없어 기본 계획만 생성했습니다.",
            "steps": [],
        }

    short_description = _truncate(job.job_description, PLAN_DESCRIPTION_MAX_CHARS)
    return {
        "summary": f"{job.job_title} 작업을 {preferred.name} 에이전트로 수행합니다.",
        "steps": [
            {
                "agent_id": preferred.agent_id,
                "agent_name": preferred.name,
                "tool_name": "",
                "tool_params": {},
                "description": short_description,
            }
        ],
    }


def _agent_by_id(agents: list[AgentDefinition], agent_id: str) -> AgentDefinition | None:
    return next((agent for agent in agents if agent.agent_id == agent_id), None)


async def _list_tools_for_agent(agent_manager: Any | None, definition: AgentDefinition) -> list[dict[str, str]]:
    tools: list[dict[str, str]] = []
    if definition.agent_id == INVENTORY_AGENT_ID:
        tools.append(
            {
                "name": QUERY_INVENTORY_TOOL_NAME,
                "description": "Query the inventory database",
            }
        )

    mcp_manager = getattr(agent_manager, "mcp_manager", None) if agent_manager is not None else None
    if mcp_manager is not None and definition.mcp_server_keys:
        try:
            for tool in await mcp_manager.get_tools_for_servers(definition.mcp_server_keys):
                tools.append(
                    {
                        "name": tool.name,
                        "description": getattr(tool, "description", "") or "",
                    }
                )
        except Exception as exc:
            logger.warning("Failed to list tools for %s: %s", definition.agent_id, exc)
    return tools


async def _consult_agent_for_tools(
    *,
    agent_manager: Any | None,
    definition: AgentDefinition,
    step_description: str,
    job_idx: int,
    step_index: int,
) -> tuple[str, dict[str, Any], str]:
    """Ask the selected agent (via role + tool catalog) which tool to use."""
    available_tools = await _list_tools_for_agent(agent_manager, definition)
    record_orchestration(
        agent_id=JOB_PLANNING_AGENT.agent_id,
        agent_name=JOB_PLANNING_AGENT.name,
        event="tool_consult_start",
        detail=(
            f"consulting={definition.name} ({definition.agent_id})\n"
            f"tools_available={len(available_tools)}\n"
            f"step_description={step_description}"
        ),
        job_idx=job_idx,
        step_index=step_index,
    )

    if not available_tools:
        fallback_params = {"message": step_description}
        record_orchestration(
            agent_id=JOB_PLANNING_AGENT.agent_id,
            agent_name=JOB_PLANNING_AGENT.name,
            event="tool_consult_result",
            detail=f"target={definition.agent_id} status=no_tools_fallback",
            response=json.dumps({"tool_name": "agent_invoke", "tool_params": fallback_params}, ensure_ascii=False),
            job_idx=job_idx,
            step_index=step_index,
        )
        return "agent_invoke", fallback_params, "no tools available"

    tools_json = json.dumps(available_tools, ensure_ascii=False)
    consult_prompt = (
        f"Step instruction: {step_description}\n\n"
        f"Available tools:\n{tools_json}"
    )
    system_prompt = (
        f"You are the agent '{definition.name}' (id={definition.agent_id}). "
        f"Your role: {definition.role}\n\n"
        f"{TOOL_CONSULT_SYSTEM_PROMPT}"
    )

    # Token + prompt-debug attribution: sys-job-planning (orchestration cost).
    # The system prompt still role-plays the consult target for tool selection quality.
    try:
        with prompt_debug_scope(
            job_idx=job_idx,
            caller_agent_id=JOB_PLANNING_AGENT.agent_id,
            caller_agent_name=JOB_PLANNING_AGENT.name,
            step_index=step_index,
        ):
            llm = wrap_llm_for_prompt_debug(
                get_llm(),
                agent_id=JOB_PLANNING_AGENT.agent_id,
                agent_name=JOB_PLANNING_AGENT.name,
            )
            response = await llm.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=consult_prompt),
                ]
            )
        content = response.content if isinstance(response.content, str) else str(response.content)
        parsed = _extract_json_block(content) or {}
        tool_name = str(parsed.get("tool_name") or "").strip()
        tool_params = parsed.get("tool_params") if isinstance(parsed.get("tool_params"), dict) else {}
        rationale = str(parsed.get("rationale") or "").strip()

        allowed_names = {tool["name"] for tool in available_tools} | {"agent_invoke"}
        if tool_name not in allowed_names:
            tool_name = available_tools[0]["name"] if available_tools else "agent_invoke"
            rationale = (rationale + " ; invalid tool_name remapped").strip(" ;")

        record_orchestration(
            agent_id=JOB_PLANNING_AGENT.agent_id,
            agent_name=JOB_PLANNING_AGENT.name,
            event="tool_consult_result",
            detail=f"target={definition.agent_id} tool={tool_name}",
            response=json.dumps(
                {"tool_name": tool_name, "tool_params": tool_params, "rationale": rationale},
                ensure_ascii=False,
            )[:2000],
            job_idx=job_idx,
            step_index=step_index,
            output_tokens=estimate_tokens(content),
        )
        return tool_name, tool_params, rationale
    except Exception as exc:
        logger.warning("Tool consult failed for %s: %s", definition.agent_id, exc)
        fallback_params = {"message": step_description}
        record_orchestration(
            agent_id=JOB_PLANNING_AGENT.agent_id,
            agent_name=JOB_PLANNING_AGENT.name,
            event="tool_consult_failed",
            detail=f"target={definition.agent_id} error={exc}",
            job_idx=job_idx,
            step_index=step_index,
        )
        return "agent_invoke", fallback_params, str(exc)


async def _enrich_plan_with_tool_consultations(
    plan: dict[str, Any],
    *,
    agents: list[AgentDefinition],
    agent_manager: Any | None,
    job_idx: int,
) -> dict[str, Any]:
    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    enriched: list[dict[str, Any]] = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue
        item = dict(step)
        agent_id = str(item.get("agent_id") or "")
        definition = _agent_by_id(agents, agent_id)
        if definition is None and agent_manager is not None:
            try:
                definition = agent_manager.get_definition(agent_id)
            except Exception:
                definition = None

        description = str(item.get("description") or "")
        if definition is None:
            item["tool_name"] = item.get("tool_name") or "agent_invoke"
            item["tool_params"] = item.get("tool_params") if isinstance(item.get("tool_params"), dict) else {
                "message": description
            }
            enriched.append(item)
            continue

        item.setdefault("agent_name", definition.name)
        tool_name, tool_params, _rationale = await _consult_agent_for_tools(
            agent_manager=agent_manager,
            definition=definition,
            step_description=description,
            job_idx=job_idx,
            step_index=index,
        )
        item["tool_name"] = tool_name
        item["tool_params"] = tool_params
        enriched.append(item)

    return {**plan, "steps": enriched}


async def _generate_plan(
    job: Job,
    agents: list[AgentDefinition],
    *,
    agent_manager: Any | None = None,
) -> dict[str, Any]:
    catalog = [
        {
            "agent_id": agent.agent_id,
            "name": agent.name,
            "role": agent.role,
            "mcp_servers": agent.mcp_server_keys,
        }
        for agent in agents
    ]
    prompt = (
        f"Job title: {job.job_title}\n"
        f"Description: {job.job_description}\n"
        f"Requester: {job.requester} ({job.request_depart})\n"
        f"Approver: {job.approver}\n"
        f"Available agents: {json.dumps(catalog, ensure_ascii=False)}"
    )

    record_orchestration(
        agent_id=JOB_PLANNING_AGENT.agent_id,
        agent_name=JOB_PLANNING_AGENT.name,
        event="planning_start",
        detail=(
            f"title={job.job_title}\n"
            f"description_chars={len(job.job_description)} "
            f"~tokens={estimate_tokens(job.job_description)}\n"
            f"agents={len(agents)}"
        ),
        job_idx=job.idx,
        input_tokens=estimate_tokens(prompt),
    )

    plan: dict[str, Any] | None = None
    source = "fallback"
    try:
        with prompt_debug_scope(job_idx=job.idx):
            llm = wrap_llm_for_prompt_debug(
                get_llm(),
                agent_id=JOB_PLANNING_AGENT.agent_id,
                agent_name=JOB_PLANNING_AGENT.name,
            )
            messages = [
                SystemMessage(content=PLANNING_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
            response = await llm.ainvoke(messages)
        content = response.content if isinstance(response.content, str) else str(response.content)
        parsed = _extract_json_block(content)
        if parsed and isinstance(parsed.get("steps"), list):
            plan = _normalize_plan(parsed)
            source = "llm"
            record_orchestration(
                agent_id=JOB_PLANNING_AGENT.agent_id,
                agent_name=JOB_PLANNING_AGENT.name,
                event="agent_selection_complete",
                detail=_plan_summary_detail(plan, source="llm_agents_only"),
                response=json.dumps(plan, ensure_ascii=False)[:2000],
                job_idx=job.idx,
                output_tokens=estimate_tokens(content),
            )
    except Exception as exc:
        logger.warning("LLM plan generation failed, using fallback: %s", exc)
        record_orchestration(
            agent_id=JOB_PLANNING_AGENT.agent_id,
            agent_name=JOB_PLANNING_AGENT.name,
            event="planning_llm_failed",
            detail=str(exc),
            job_idx=job.idx,
        )

    if plan is None:
        plan = _normalize_plan(_build_fallback_plan(job, agents))
        source = "fallback"
        record_orchestration(
            agent_id=JOB_PLANNING_AGENT.agent_id,
            agent_name=JOB_PLANNING_AGENT.name,
            event="agent_selection_complete",
            detail=_plan_summary_detail(plan, source="fallback_agents_only"),
            response=json.dumps(plan, ensure_ascii=False)[:2000],
            job_idx=job.idx,
        )

    plan = await _enrich_plan_with_tool_consultations(
        plan,
        agents=agents,
        agent_manager=agent_manager,
        job_idx=job.idx,
    )
    record_orchestration(
        agent_id=JOB_PLANNING_AGENT.agent_id,
        agent_name=JOB_PLANNING_AGENT.name,
        event="planning_complete",
        detail=_plan_summary_detail(plan, source=f"{source}+tool_consult"),
        response=json.dumps(plan, ensure_ascii=False)[:2000],
        job_idx=job.idx,
    )
    return plan


async def _notify_approver(
    database_path: Path,
    *,
    job: Job,
    approver: str,
    notify_channel: NotifyChannel,
) -> None:
    await send_job_notifications(
        database_path,
        channel=notify_channel,
        recipients=[approver],
        title="작업검토요청",
        message=f"[{job.job_title}] 작업 계획이 수립되었습니다. 검토해 주세요.",
        job_idx=job.idx,
        notification_type=NOTIFICATION_TYPE_REVIEW_REQUEST,
    )


async def submit_job_request(
    database_path: Path,
    *,
    request_date: str,
    job_title: str,
    request_depart: str,
    requester: str,
    requester_email: str,
    completion_request_date: str,
    job_description: str,
    approver: str,
    notify_channel: NotifyChannel = NotifyChannel.INTEGRATED_CHAT,
    agent_manager: Any | None = None,
) -> Job:
    job = create_job(
        database_path,
        request_date=request_date,
        job_title=job_title,
        request_depart=request_depart,
        requester=requester,
        requester_email=requester_email,
        completion_request_date=completion_request_date,
        job_description=job_description,
        approver=approver,
        state=JOB_STATE_RECEIVED,
        notify_channel=notify_channel.value,
    )

    agents = load_agent_definitions(database_path)
    plan = await _generate_plan(job, agents, agent_manager=agent_manager)
    plan_json = json.dumps(plan, ensure_ascii=False)
    updated = update_job_plan(database_path, job.idx, plan_json, JOB_STATE_PLAN_COMPLETED)
    if updated is None:
        raise RuntimeError("Failed to update job plan")

    await _notify_approver(
        database_path,
        job=updated,
        approver=approver,
        notify_channel=notify_channel,
    )

    logger.info("%s processed job idx=%s", JOB_PLANNING_AGENT.name, updated.idx)
    return updated
