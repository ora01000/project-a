import json
import logging
import re
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from backend.app.agents.base import AgentDefinition
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
from backend.app.services.job_notifications import send_job_notifications

logger = logging.getLogger(__name__)

PLANNING_SYSTEM_PROMPT = (
    "You are the Job Planning system agent. Analyze the job request and produce an execution plan "
    "as JSON only. The JSON must have keys: summary (string), steps (array). "
    "Each step must include: agent_id, agent_name, tool_name, tool_params (object), description. "
    "Use only agent_id values from the provided agent catalog. "
    "Respond with valid JSON only, no markdown."
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


def _build_fallback_plan(job: Job, agents: list[AgentDefinition]) -> dict[str, Any]:
    preferred = next((agent for agent in agents if "k8s" in agent.agent_id), agents[0] if agents else None)
    if preferred is None:
        return {
            "summary": "등록된 에이전트가 없어 기본 계획만 생성했습니다.",
            "steps": [],
        }

    return {
        "summary": f"{job.job_title} 작업을 {preferred.name} 에이전트로 수행합니다.",
        "steps": [
            {
                "agent_id": preferred.agent_id,
                "agent_name": preferred.name,
                "tool_name": "agent_invoke",
                "tool_params": {"message": job.job_description[:500]},
                "description": job.job_description[:200],
            }
        ],
    }


async def _generate_plan(job: Job, agents: list[AgentDefinition]) -> dict[str, Any]:
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

    try:
        llm = get_llm()
        response = await llm.ainvoke(
            [
                SystemMessage(content=PLANNING_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
        )
        content = response.content if isinstance(response.content, str) else str(response.content)
        parsed = _extract_json_block(content)
        if parsed and isinstance(parsed.get("steps"), list):
            return parsed
    except Exception as exc:
        logger.warning("LLM plan generation failed, using fallback: %s", exc)

    return _build_fallback_plan(job, agents)


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
    plan = await _generate_plan(job, agents)
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
