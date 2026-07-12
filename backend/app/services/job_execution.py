import json
import logging
from pathlib import Path
from typing import Any

from backend.app.services.agent_invocation import AgentInvocationError, invoke_agent_by_id
from backend.app.agents.system_agents import JOB_EXECUTION_AGENT, NotifyChannel
from backend.app.db.jobs import (
    JOB_STATE_APPROVED,
    JOB_STATE_COMPLETED,
    JOB_STATE_REJECTED,
    Job,
    get_job_by_idx,
    update_job_execution_result,
    update_job_state,
)
from backend.app.db.notifications import (
    NOTIFICATION_TYPE_EXECUTION_RESULT,
    NOTIFICATION_TYPE_REJECTION,
    create_job_notification,
)
from backend.app.db.users import list_users
from backend.app.notifications.channels import dispatch_job_notification
from backend.app.services.job_notifications import parse_notify_channel, send_job_notifications

logger = logging.getLogger(__name__)


def _parse_plan(job: Job) -> dict[str, Any]:
    if not job.job_plan:
        return {"summary": "", "steps": []}
    try:
        return json.loads(job.job_plan)
    except json.JSONDecodeError:
        return {"summary": job.job_plan, "steps": []}


def _find_registered_users(database_path: Path, *identifiers: str) -> list[tuple[str, str]]:
    normalized = {value.strip() for value in identifiers if value and value.strip()}
    matches: list[tuple[str, str]] = []
    for user in list_users(database_path):
        if user.userid in normalized or user.username in normalized:
            matches.append((user.userid, user.username))
    return matches


async def mark_job_under_review(database_path: Path, job_idx: int) -> Job | None:
    from backend.app.db.jobs import JOB_STATE_UNDER_REVIEW

    return update_job_state(database_path, job_idx, JOB_STATE_UNDER_REVIEW)


async def reject_job(database_path: Path, job_idx: int, reason: str = "") -> Job | None:
    job = get_job_by_idx(database_path, job_idx)
    if job is None:
        return None

    updated = update_job_state(database_path, job_idx, JOB_STATE_REJECTED)
    if updated is None:
        return None

    message = reason or f"[{job.job_title}] 작업이 반려되었습니다."
    await dispatch_job_notification(
        database_path=database_path,
        channel=NotifyChannel.EMAIL,
        target=job.requester_email,
        title="작업 반려",
        message=message,
        job_idx=job_idx,
    )
    await dispatch_job_notification(
        database_path=database_path,
        channel=NotifyChannel.TEAMS,
        target=job.requester_email,
        title="작업 반려",
        message=message,
        job_idx=job_idx,
    )

    for userid, username in _find_registered_users(database_path, job.requester):
        for target in {userid, username}:
            create_job_notification(
                database_path,
                job_idx=job_idx,
                target_user=target,
                notification_type=NOTIFICATION_TYPE_REJECTION,
                title="작업 반려",
                message=message,
            )

    return updated


async def hold_job(database_path: Path, job_idx: int) -> Job | None:
    from backend.app.db.jobs import JOB_STATE_PENDING

    logger.info("Hold job requested for idx=%s (stub)", job_idx)
    return update_job_state(database_path, job_idx, JOB_STATE_PENDING)


async def execute_job(database_path: Path, job_idx: int, agent_manager: Any) -> Job | None:
    job = get_job_by_idx(database_path, job_idx)
    if job is None:
        return None

    update_job_state(database_path, job_idx, JOB_STATE_APPROVED)
    plan = _parse_plan(job)
    step_results: list[dict[str, Any]] = []

    for step in plan.get("steps", []):
        agent_id = str(step.get("agent_id", ""))
        description = str(step.get("description", job.job_description))
        if agent_id not in agent_manager.agents:
            if hasattr(agent_manager, "mark_agent_error"):
                agent_manager.mark_agent_error(
                    agent_id,
                    f"Agent '{agent_id}' not found during job execution",
                    input_message=description,
                )
            step_results.append(
                {
                    "agent_id": agent_id,
                    "status": "skipped",
                    "content": f"에이전트 '{agent_id}'를 찾을 수 없습니다.",
                }
            )
            continue

        try:
            if hasattr(agent_manager, "mark_agent_working"):
                agent_manager.mark_agent_working(agent_id)
            result = await invoke_agent_by_id(
                agent_manager,
                agent_id,
                description,
                caller_agent_id=JOB_EXECUTION_AGENT.agent_id,
            )
            step_results.append(
                {
                    "agent_id": agent_id,
                    "agent_name": step.get("agent_name", agent_id),
                    "tool_name": step.get("tool_name"),
                    "tool_params": step.get("tool_params", {}),
                    "status": "completed",
                    "content": result.content,
                }
            )
            if hasattr(agent_manager, "mark_agent_idle"):
                agent_manager.mark_agent_idle(agent_id)
        except AgentInvocationError as exc:
            if hasattr(agent_manager, "mark_agent_error"):
                agent_manager.mark_agent_error(
                    agent_id,
                    str(exc),
                    input_message=description,
                )
            step_results.append(
                {
                    "agent_id": agent_id,
                    "status": "failed",
                    "content": str(exc),
                }
            )
        except Exception as exc:
            if hasattr(agent_manager, "mark_agent_error"):
                agent_manager.mark_agent_error(
                    agent_id,
                    str(exc),
                    input_message=description,
                )
            step_results.append(
                {
                    "agent_id": agent_id,
                    "status": "failed",
                    "content": str(exc),
                }
            )

    execution_payload = {
        "summary": plan.get("summary", ""),
        "results": step_results,
    }
    execution_json = json.dumps(execution_payload, ensure_ascii=False)
    completed = update_job_execution_result(
        database_path,
        job_idx,
        execution_json,
        JOB_STATE_COMPLETED,
    )
    if completed is None:
        return None

    result_message = (
        f"[{completed.job_title}] 작업 수행이 완료되었습니다.\n"
        f"{execution_payload['summary']}"
    )

    notify_channel = parse_notify_channel(completed.notify_channel)
    await send_job_notifications(
        database_path,
        channel=notify_channel,
        recipients=[completed.approver, completed.requester],
        title="작업 수행 완료",
        message=result_message,
        job_idx=job_idx,
        notification_type=NOTIFICATION_TYPE_EXECUTION_RESULT,
        fallback_emails=[completed.requester_email],
    )

    logger.info("%s completed job idx=%s", JOB_EXECUTION_AGENT.name, job_idx)
    return completed
