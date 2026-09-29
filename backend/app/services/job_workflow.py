"""Build job workflow steps for the detail panel workflow tab."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.app.db.jobs import (
    JOB_STATUS_APPROVER_ASSIGNED,
    JOB_STATUS_CANCELLED,
    JOB_STATUS_COMPLETED_FAILURE,
    JOB_STATUS_COMPLETED_SUCCESS,
    JOB_STATUS_DIRECT_APPROVED,
    JOB_STATUS_RECEIVED,
    JOB_STATUS_REJECTED,
    JOB_TYPE_SIGNUP,
    JobRecord,
    list_jobs_for_workflow,
)
from backend.app.db.jobs_result import JobResultRecord, get_job_result_by_srnum
from backend.app.db.roles import is_admin_role
from backend.app.db.users import get_user_by_userid


@dataclass(frozen=True)
class JobWorkflowStep:
    status_code: int
    label: str
    timestamp: str | None
    detail: str = ""


@dataclass(frozen=True)
class JobWorkflowItem:
    idx: int
    srnum: str
    requester_name: str
    requester_userid: str
    approver: str | None
    approver_name: str
    status_code: int
    steps: tuple[JobWorkflowStep, ...]


def _resolve_display_name(database_path: str | Path, userid: str) -> str:
    normalized = userid.strip()
    if not normalized:
        return ""
    user = get_user_by_userid(database_path, normalized)
    if user is not None and user.username.strip():
        return user.username.strip()
    return normalized


def _should_show_agent_request_step(job: JobRecord) -> bool:
    if job.job_type == JOB_TYPE_SIGNUP:
        return False
    status = job.status_code
    if status == JOB_STATUS_DIRECT_APPROVED:
        return True
    if status == JOB_STATUS_CANCELLED:
        return True
    if status >= JOB_STATUS_COMPLETED_SUCCESS:
        return True
    return False


def build_job_workflow_steps(
    job: JobRecord,
    result: JobResultRecord | None,
    *,
    approver_name: str = "",
) -> tuple[JobWorkflowStep, ...]:
    steps: list[JobWorkflowStep] = []
    status = job.status_code
    has_approver = bool((job.approver or "").strip())

    steps.append(
        JobWorkflowStep(
            status_code=JOB_STATUS_RECEIVED,
            label="접수",
            timestamp=job.received_at,
        )
    )

    if has_approver:
        steps.append(
            JobWorkflowStep(
                status_code=JOB_STATUS_APPROVER_ASSIGNED,
                label="승인자 지정",
                timestamp=job.approver_registered_date,
                detail=approver_name or (job.approver or "").strip(),
            )
        )

    if status == JOB_STATUS_REJECTED:
        steps.append(
            JobWorkflowStep(
                status_code=JOB_STATUS_REJECTED,
                label="작업반려",
                timestamp=None,
            )
        )
        return tuple(steps)

    if _should_show_agent_request_step(job):
        steps.append(
            JobWorkflowStep(
                status_code=JOB_STATUS_DIRECT_APPROVED,
                label="에이전트 처리 요청",
                timestamp=None,
            )
        )

    if status == JOB_STATUS_COMPLETED_SUCCESS:
        steps.append(
            JobWorkflowStep(
                status_code=JOB_STATUS_COMPLETED_SUCCESS,
                label="처리완료",
                timestamp=result.complete_date if result is not None else None,
            )
        )
    elif status == JOB_STATUS_COMPLETED_FAILURE:
        steps.append(
            JobWorkflowStep(
                status_code=JOB_STATUS_COMPLETED_FAILURE,
                label="처리실패",
                timestamp=result.complete_date if result is not None else None,
            )
        )
    elif status == JOB_STATUS_CANCELLED:
        steps.append(
            JobWorkflowStep(
                status_code=JOB_STATUS_CANCELLED,
                label="작업취소",
                timestamp=None,
            )
        )

    return tuple(steps)


def list_job_workflows(
    database_path: str | Path,
    *,
    viewer_userid: str,
    viewer_role: int,
) -> list[JobWorkflowItem]:
    exclude_signup = not is_admin_role(viewer_role)
    jobs = list_jobs_for_workflow(
        database_path,
        viewer_userid=viewer_userid,
        viewer_role=viewer_role,
        exclude_job_type=JOB_TYPE_SIGNUP if exclude_signup else None,
    )

    items: list[JobWorkflowItem] = []
    for job in jobs:
        approver_name = ""
        if (job.approver or "").strip():
            approver_name = _resolve_display_name(database_path, job.approver or "")

        result: JobResultRecord | None = None
        if job.status_code >= JOB_STATUS_COMPLETED_SUCCESS:
            result = get_job_result_by_srnum(database_path, job.srnum)

        steps = build_job_workflow_steps(
            job,
            result,
            approver_name=approver_name,
        )
        items.append(
            JobWorkflowItem(
                idx=job.idx,
                srnum=job.srnum,
                requester_name=job.requester_name,
                requester_userid=job.madang_id,
                approver=job.approver,
                approver_name=approver_name,
                status_code=job.status_code,
                steps=steps,
            )
        )
    return items
