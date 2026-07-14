import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from backend.app.services.agent_invocation import AgentInvocationError, invoke_agent_by_id
from backend.app.agents.system_agents import JOB_EXECUTION_AGENT, NotifyChannel
from backend.app.db.jobs import (
    JOB_STATE_APPROVED,
    JOB_STATE_COMPLETED,
    JOB_STATE_FAILED,
    JOB_STATE_PENDING,
    JOB_STATE_PLAN_COMPLETED,
    JOB_STATE_REJECTED,
    JOB_STATE_UNDER_REVIEW,
    Job,
    get_job_by_idx,
    job_state_label,
    update_job_execution_result,
    update_job_state,
)
from backend.app.db.notifications import (
    NOTIFICATION_TYPE_EXECUTION_FAILURE,
    NOTIFICATION_TYPE_EXECUTION_RESULT,
    NOTIFICATION_TYPE_REJECTION,
    NOTIFICATION_TYPE_REVIEW_REQUEST,
    create_job_notification,
    delete_job_notifications_by_job,
)
from backend.app.db.users import list_users
from backend.app.notifications.channels import dispatch_job_notification
from backend.app.services.job_notifications import parse_notify_channel, send_job_notifications

logger = logging.getLogger(__name__)

_running_job_idxs: set[int] = set()
_running_lock = asyncio.Lock()

APPROVE_ALLOWED_STATES = {
    JOB_STATE_PLAN_COMPLETED,
    JOB_STATE_UNDER_REVIEW,
    JOB_STATE_PENDING,
}
RETRY_ALLOWED_STATES = {JOB_STATE_FAILED}


class JobExecutionConflictError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class JobExecutionNotAllowedError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


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


def _step_agent_label(result: dict[str, Any]) -> str:
    agent_name = str(result.get("agent_name") or "").strip()
    agent_id = str(result.get("agent_id") or "").strip()
    if agent_name and agent_id and agent_name != agent_id:
        return f"{agent_name} ({agent_id})"
    return agent_name or agent_id or "unknown"


def _format_execution_result_message(job_title: str, step_results: list[dict[str, Any]], *, summary: str) -> str:
    sections = [f"[{job_title}] 작업 수행이 완료되었습니다."]
    summary_text = summary.strip()
    if summary_text:
        sections.append(f"요약: {summary_text}")

    answer_blocks: list[str] = []
    for index, result in enumerate(step_results, start=1):
        content = str(result.get("content") or "").strip() or "(응답 없음)"
        answer_blocks.append(f"{index}. {_step_agent_label(result)}\n{content}")
    if answer_blocks:
        sections.append("에이전트 답변:\n" + "\n\n".join(answer_blocks))
    return "\n\n".join(sections)


def _format_execution_failure_message(job_title: str, step_results: list[dict[str, Any]]) -> str:
    sections = [f"[{job_title}] 작업 수행이 실패했습니다."]
    failure_blocks: list[str] = []
    for index, result in enumerate(step_results, start=1):
        status = str(result.get("status") or "")
        if status == "completed":
            continue
        reason = str(result.get("content") or "").strip() or "알 수 없는 오류"
        status_label = "건너뜀" if status == "skipped" else "실패"
        failure_blocks.append(
            f"{index}. {_step_agent_label(result)} ({status_label})\n실패 사유: {reason}"
        )
    if failure_blocks:
        sections.append("실패 사유:\n" + "\n\n".join(failure_blocks))
    return "\n\n".join(sections)


async def mark_job_under_review(database_path: Path, job_idx: int) -> Job | None:
    return update_job_state(database_path, job_idx, JOB_STATE_UNDER_REVIEW)


async def reject_job(database_path: Path, job_idx: int, reason: str = "") -> Job | None:
    job = get_job_by_idx(database_path, job_idx)
    if job is None:
        return None

    updated = update_job_state(database_path, job_idx, JOB_STATE_REJECTED)
    if updated is None:
        return None

    delete_job_notifications_by_job(
        database_path,
        job_idx,
        notification_type=NOTIFICATION_TYPE_REVIEW_REQUEST,
    )

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

    for userid, _username in _find_registered_users(database_path, job.requester):
        create_job_notification(
            database_path,
            job_idx=job_idx,
            target_user=userid,
            notification_type=NOTIFICATION_TYPE_REJECTION,
            title="작업 반려",
            message=message,
        )

    return updated


async def hold_job(database_path: Path, job_idx: int) -> Job | None:
    logger.info("Hold job requested for idx=%s (stub)", job_idx)
    updated = update_job_state(database_path, job_idx, JOB_STATE_PENDING)
    if updated is not None:
        delete_job_notifications_by_job(
            database_path,
            job_idx,
            notification_type=NOTIFICATION_TYPE_REVIEW_REQUEST,
        )
    return updated


def _validate_accept_state(job: Job, *, is_retry: bool) -> None:
    allowed = RETRY_ALLOWED_STATES if is_retry else APPROVE_ALLOWED_STATES
    if job.state in allowed:
        return
    action = "재작업" if is_retry else "승인"
    raise JobExecutionNotAllowedError(
        f"현재 상태({job_state_label(job.state)})에서는 {action}할 수 없습니다."
    )


async def accept_job_execution(
    database_path: Path,
    job_idx: int,
    *,
    is_retry: bool = False,
) -> Job | None:
    """Mark job as approved and clear related notifications. Does not run agents."""
    async with _running_lock:
        job = get_job_by_idx(database_path, job_idx)
        if job is None:
            return None
        if job_idx in _running_job_idxs:
            raise JobExecutionConflictError("이미 수행 중인 작업입니다.")
        _validate_accept_state(job, is_retry=is_retry)
        _running_job_idxs.add(job_idx)

    try:
        updated = update_job_state(database_path, job_idx, JOB_STATE_APPROVED)
        if updated is None:
            async with _running_lock:
                _running_job_idxs.discard(job_idx)
            return None

        delete_job_notifications_by_job(
            database_path,
            job_idx,
            notification_type=NOTIFICATION_TYPE_REVIEW_REQUEST,
        )
        delete_job_notifications_by_job(
            database_path,
            job_idx,
            notification_type=NOTIFICATION_TYPE_EXECUTION_FAILURE,
        )
        return updated
    except Exception:
        async with _running_lock:
            _running_job_idxs.discard(job_idx)
        raise


async def run_approved_job(database_path: Path, job_idx: int, agent_manager: Any) -> Job | None:
    """Run agent steps for an already-accepted (approved) job and notify recipients."""
    try:
        job = get_job_by_idx(database_path, job_idx)
        if job is None:
            return None

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
                        "agent_name": step.get("agent_name", agent_id),
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
                        "agent_name": step.get("agent_name", agent_id),
                        "tool_name": step.get("tool_name"),
                        "tool_params": step.get("tool_params", {}),
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
                        "agent_name": step.get("agent_name", agent_id),
                        "tool_name": step.get("tool_name"),
                        "tool_params": step.get("tool_params", {}),
                        "status": "failed",
                        "content": str(exc),
                    }
                )

        execution_payload = {
            "summary": plan.get("summary", ""),
            "results": step_results,
        }
        execution_json = json.dumps(execution_payload, ensure_ascii=False)
        is_failed = bool(step_results) and any(
            str(result.get("status", "")) != "completed" for result in step_results
        )
        final_state = JOB_STATE_FAILED if is_failed else JOB_STATE_COMPLETED
        completed = update_job_execution_result(
            database_path,
            job_idx,
            execution_json,
            final_state,
        )
        if completed is None:
            return None

        if is_failed:
            failure_message = _format_execution_failure_message(completed.job_title, step_results)
            await send_job_notifications(
                database_path,
                channel=NotifyChannel.INTEGRATED_CHAT,
                recipients=[completed.approver],
                title="작업 수행 실패",
                message=failure_message,
                job_idx=job_idx,
                notification_type=NOTIFICATION_TYPE_EXECUTION_FAILURE,
            )
            logger.warning("%s failed job idx=%s", JOB_EXECUTION_AGENT.name, job_idx)
            return completed

        result_message = _format_execution_result_message(
            completed.job_title,
            step_results,
            summary=str(execution_payload.get("summary") or ""),
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
    finally:
        async with _running_lock:
            _running_job_idxs.discard(job_idx)


async def _run_approved_job_safe(database_path: Path, job_idx: int, agent_manager: Any) -> None:
    try:
        await run_approved_job(database_path, job_idx, agent_manager)
    except Exception:
        logger.exception("%s background execution crashed for job idx=%s", JOB_EXECUTION_AGENT.name, job_idx)
        async with _running_lock:
            _running_job_idxs.discard(job_idx)


async def accept_and_schedule_job_execution(
    database_path: Path,
    job_idx: int,
    agent_manager: Any,
    *,
    is_retry: bool = False,
) -> Job | None:
    """Accept the job immediately and schedule agent execution in the background."""
    accepted = await accept_job_execution(database_path, job_idx, is_retry=is_retry)
    if accepted is None:
        return None

    asyncio.create_task(
        _run_approved_job_safe(database_path, job_idx, agent_manager),
        name=f"job-execution-{job_idx}",
    )
    logger.info(
        "%s accepted job idx=%s (async execution scheduled, retry=%s)",
        JOB_EXECUTION_AGENT.name,
        job_idx,
        is_retry,
    )
    return accepted
