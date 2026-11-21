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
    requester_idx: int
    requester_name: str
    requester_userid: str
    approver_idx: int | None
    approver_userid: str | None
    approver_name: str
    status_code: int
    steps: tuple[JobWorkflowStep, ...]
    is_scheduled: bool = False
    scheduled_at: str | None = None
    schedule_waiting: bool = False


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
    schedule_waiting: bool = False,
) -> tuple[JobWorkflowStep, ...]:
    steps: list[JobWorkflowStep] = []
    status = job.status_code
    has_approver = job.approver_idx is not None

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
                detail=approver_name or (job.approver_userid or "").strip(),
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
        if schedule_waiting:
            steps.append(
                JobWorkflowStep(
                    status_code=JOB_STATUS_DIRECT_APPROVED,
                    label="계획 작업",
                    timestamp=job.scheduled_at,
                    detail="예정",
                )
            )
        else:
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
    viewer_idx: int | None,
    viewer_role: int,
) -> list[JobWorkflowItem]:
    from backend.app.db.jobs_scheduled import list_scheduled_job_idxs

    exclude_signup = not is_admin_role(viewer_role)
    jobs = list_jobs_for_workflow(
        database_path,
        viewer_idx=viewer_idx,
        viewer_role=viewer_role,
        exclude_job_type=JOB_TYPE_SIGNUP if exclude_signup else None,
    )
    waiting_idxs = list_scheduled_job_idxs(database_path)

    items: list[JobWorkflowItem] = []
    for job in jobs:
        approver_name = (job.approver_name or job.approver_userid or "").strip()

        result: JobResultRecord | None = None
        if job.status_code >= JOB_STATUS_COMPLETED_SUCCESS:
            result = get_job_result_by_srnum(database_path, job.srnum)

        schedule_waiting = bool(job.is_scheduled) and job.idx in waiting_idxs
        steps = build_job_workflow_steps(
            job,
            result,
            approver_name=approver_name,
            schedule_waiting=schedule_waiting,
        )
        items.append(
            JobWorkflowItem(
                idx=job.idx,
                srnum=job.srnum,
                requester_idx=job.requester_idx,
                requester_name=job.requester_name,
                requester_userid=job.requester_userid,
                approver_idx=job.approver_idx,
                approver_userid=job.approver_userid,
                approver_name=approver_name,
                status_code=job.status_code,
                steps=steps,
                is_scheduled=bool(job.is_scheduled),
                scheduled_at=job.scheduled_at,
                schedule_waiting=schedule_waiting,
            )
        )
    return items
