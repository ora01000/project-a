"""Job request intake API (Teams / Power Automate inbound)."""

from __future__ import annotations

import logging
import re
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, model_validator

from backend.app.db.jobs import (
    JOB_STATUS_APPROVER_ASSIGNED,
    JOB_STATUS_CANCELLED,
    JOB_STATUS_RECEIVED,
    JOB_STATUS_REJECTED,
    JOB_TYPE_AX_INFRA,
    JOB_TYPE_SIGNUP,
    JOB_TYPE_WORKFLOW,
    JobRecord,
    approve_assigned_job,
    assign_job_approver,
    can_view_job,
    cancel_failed_job,
    direct_approve_job,
    ensure_workflow_job_result,
    get_job_by_idx,
    list_jobs,
    reject_assigned_job,
    reject_received_job,
    rework_job,
    update_job_ai_audit_comment,
)
from backend.app.db.jobs_result import JobResultRecord, get_job_result_by_srnum, upsert_job_result
from backend.app.db.roles import is_admin_role
from backend.app.middleware.session_auth import get_request_auth_user
from backend.app.notifications.email_recipients import (
    SendEmailRecipientsRequest,
    SendMarkdownEmailResponse,
    resolve_email_recipients,
)
from backend.app.notifications.email_sender import (
    build_job_result_report_markdown,
    compose_report_markdown,
    send_ax_infra_job_cancellation_email,
    send_ax_infra_job_rejection_email,
    send_job_report_emails,
)
from backend.app.db.users import get_user_by_userid
from backend.app.services.user_signup import notify_signup_approved
from backend.app.services.workflow_runner import (
    fail_workflow_after_rejection,
    resume_workflow_after_approval,
)
from backend.app.services.agent_runtime_client import AgentInvokeRequest
from backend.app.services.job_auditor import (
    build_job_review_message,
    resolve_job_auditor_agent_id,
    try_resolve_job_auditor_runtime_record,
)
from backend.app.services.job_intake import receive_job_request
from backend.app.services.job_workflow import JobWorkflowItem, JobWorkflowStep, list_job_workflows

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jobs"])


async def _notify_signup_job_approved(database_path, job: JobRecord) -> None:
    if job.job_type != JOB_TYPE_SIGNUP:
        return
    userid = (job.madang_id or "").strip()
    if not userid:
        return
    user = get_user_by_userid(database_path, userid)
    if user is None:
        logger.warning("Signup approval email skipped: user not found for madang_id=%s", userid)
        return
    await notify_signup_approved(database_path, user)


async def _resume_workflow_job_if_needed(request: Request, job: JobRecord) -> None:
    if int(job.job_type) != JOB_TYPE_WORKFLOW:
        return
    database_path = request.app.state.database_path
    try:
        result = await resume_workflow_after_approval(
            database_path=database_path,
            agent_runtime=request.app.state.agent_runtime,
            job=job,
        )
        if result is None:
            logger.warning("workflow resume skipped (no cursor) job=%s", job.idx)
            fail_workflow_after_rejection(database_path, job)
            return
        logger.info(
            "workflow resumed after approval job=%s status=%s message=%s",
            job.idx,
            result.status,
            result.message,
        )
        _update_workflow_job_result_after_resume(database_path, job, result)
        if result.status == "failed":
            logger.warning("workflow continued but failed job=%s: %s", job.idx, result.message)
    except Exception:
        logger.exception("workflow resume after approval failed job=%s", job.idx)
        try:
            fail_workflow_after_rejection(database_path, job)
        except Exception:
            logger.exception("workflow fail fallback after resume error failed job=%s", job.idx)


def _update_workflow_job_result_after_resume(database_path, job: JobRecord, run_result) -> None:
    """Append workflow continuation outcome onto the HITL job result."""
    from backend.app.db.job_datetime import now_job_datetime

    existing = get_job_result_by_srnum(database_path, job.srnum)
    base = (existing.result if existing is not None else job.job_content or "").strip()
    step_lines: list[str] = []
    for step in getattr(run_result, "steps", None) or []:
        label = getattr(step, "label", "") or ""
        status = getattr(step, "status", "") or ""
        detail = getattr(step, "detail", "") or ""
        step_lines.append(f"- [{status}] {label}" + (f": {detail}" if detail else ""))
    steps_block = "\n".join(step_lines) if step_lines else "- (추가 단계 없음)"
    status = getattr(run_result, "status", "") or ""
    message = getattr(run_result, "message", "") or ""
    appendix = (
        f"\n\n---\n\n## 승인 이후 워크플로우 진행\n\n"
        f"- 상태: **{status}**\n"
        f"- 메시지: {message}\n\n"
        f"### 단계\n\n{steps_block}\n"
    )
    upsert_job_result(
        database_path,
        srnum=job.srnum,
        result=(base + appendix).strip(),
        complete_date=now_job_datetime(),
    )


def _fail_workflow_job_if_needed(database_path, job: JobRecord) -> None:
    if int(job.job_type) != JOB_TYPE_WORKFLOW:
        return
    try:
        fail_workflow_after_rejection(database_path, job)
    except Exception:
        logger.exception("workflow fail after rejection failed job=%s", job.idx)


class JobIntakeRequest(BaseModel):
    job_title: str = Field(min_length=1, max_length=300)
    requester_name: str = Field(min_length=1, max_length=100)
    requester_email: str = Field(min_length=1, max_length=100)
    requester_depart: str = Field(min_length=1, max_length=100)
    job_content: str = Field(min_length=1)
    request_date: str = Field(min_length=1)
    madang_id: str = Field(min_length=1, max_length=50)
    team_id: str = Field(min_length=1, max_length=50)
    channel_id: str = Field(min_length=1, max_length=120)
    message_id: str = Field(min_length=1, max_length=50)


class JobRecordResponse(BaseModel):
    idx: int
    srnum: str
    status_code: int
    job_type: int = 1
    approver_registered_date: str | None = None
    approver: str | None = None
    job_title: str
    requester_name: str
    requester_email: str
    requester_depart: str
    job_content: str
    request_date: str
    madang_id: str
    team_id: str
    channel_id: str
    message_id: str
    received_at: str
    reject_reason: str = ""
    drop_reason: str = ""
    ai_audit_comment: str = ""
    ai_audit_date: str | None = None
    ai_audit_cnt: int = 0

    @classmethod
    def from_record(cls, record: JobRecord) -> "JobRecordResponse":
        return cls(
            idx=record.idx,
            srnum=record.srnum,
            status_code=record.status_code,
            job_type=record.job_type,
            approver_registered_date=record.approver_registered_date,
            approver=record.approver,
            job_title=record.job_title,
            requester_name=record.requester_name,
            requester_email=record.requester_email,
            requester_depart=record.requester_depart,
            job_content=record.job_content,
            request_date=record.request_date,
            madang_id=record.madang_id,
            team_id=record.team_id,
            channel_id=record.channel_id,
            message_id=record.message_id,
            received_at=record.received_at,
            reject_reason=record.reject_reason,
            drop_reason=record.drop_reason,
            ai_audit_comment=record.ai_audit_comment,
            ai_audit_date=record.ai_audit_date,
            ai_audit_cnt=record.ai_audit_cnt,
        )


class JobIntakeResponse(BaseModel):
    idx: int
    srnum: str
    status_code: int
    received_at: str

    @classmethod
    def from_record(cls, record: JobRecord) -> "JobIntakeResponse":
        return cls(
            idx=record.idx,
            srnum=record.srnum,
            status_code=record.status_code,
            received_at=record.received_at,
        )


@router.post("/jobs", response_model=JobIntakeResponse, status_code=201)
async def submit_job_request(
    request: Request,
    body: JobIntakeRequest,
) -> JobIntakeResponse:
    database_path = request.app.state.database_path
    try:
        record = receive_job_request(database_path, body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Job intake failed")
        raise HTTPException(status_code=500, detail="Failed to store job request") from exc

    if record.status_code != JOB_STATUS_RECEIVED:
        raise HTTPException(status_code=500, detail="Invalid job status after intake")

    return JobIntakeResponse.from_record(record)


def _hide_signup_jobs_for_viewer(viewer_role: int) -> bool:
    return not is_admin_role(viewer_role)


@router.get("/jobs", response_model=list[JobRecordResponse])
async def list_job_records(
    request: Request,
    status_code: int | None = Query(default=None),
    min_status_code: int | None = Query(default=None),
    approver: str | None = Query(default=None),
    job_type: int | None = Query(default=None),
    exclude_status_code: int | None = Query(default=None),
) -> list[JobRecordResponse]:
    database_path = request.app.state.database_path
    viewer = get_request_auth_user(request)
    if job_type == JOB_TYPE_SIGNUP and _hide_signup_jobs_for_viewer(viewer.role):
        return []
    records = list_jobs(
        database_path,
        status_code=status_code,
        min_status_code=min_status_code,
        approver=approver,
        job_type=job_type,
        exclude_status_code=exclude_status_code,
        exclude_job_type=JOB_TYPE_SIGNUP if _hide_signup_jobs_for_viewer(viewer.role) else None,
        viewer_userid=viewer.userid,
        viewer_role=viewer.role,
    )
    return [JobRecordResponse.from_record(record) for record in records]


class JobWorkflowStepResponse(BaseModel):
    status_code: int
    label: str
    timestamp: str | None = None
    detail: str = ""

    @classmethod
    def from_step(cls, step: JobWorkflowStep) -> "JobWorkflowStepResponse":
        return cls(
            status_code=step.status_code,
            label=step.label,
            timestamp=step.timestamp,
            detail=step.detail,
        )


class JobWorkflowItemResponse(BaseModel):
    idx: int
    srnum: str
    requester_name: str
    requester_userid: str
    approver: str | None = None
    approver_name: str = ""
    status_code: int
    steps: list[JobWorkflowStepResponse]

    @classmethod
    def from_item(cls, item: JobWorkflowItem) -> "JobWorkflowItemResponse":
        return cls(
            idx=item.idx,
            srnum=item.srnum,
            requester_name=item.requester_name,
            requester_userid=item.requester_userid,
            approver=item.approver,
            approver_name=item.approver_name,
            status_code=item.status_code,
            steps=[JobWorkflowStepResponse.from_step(step) for step in item.steps],
        )


@router.get("/jobs/workflow", response_model=list[JobWorkflowItemResponse])
async def list_job_workflow_items(request: Request) -> list[JobWorkflowItemResponse]:
    database_path = request.app.state.database_path
    viewer = get_request_auth_user(request)
    items = list_job_workflows(
        database_path,
        viewer_userid=viewer.userid,
        viewer_role=viewer.role,
    )
    return [JobWorkflowItemResponse.from_item(item) for item in items]


@router.get("/jobs/{idx}", response_model=JobRecordResponse)
async def get_job_record(request: Request, idx: int) -> JobRecordResponse:
    database_path = request.app.state.database_path
    viewer = get_request_auth_user(request)
    record = get_job_by_idx(database_path, idx)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not can_view_job(job=record, viewer_userid=viewer.userid, viewer_role=viewer.role):
        raise HTTPException(status_code=404, detail="Job not found")
    return JobRecordResponse.from_record(record)


class JobResultResponse(BaseModel):
    srnum: str
    result: str
    complete_date: str

    @classmethod
    def from_record(cls, record: JobResultRecord) -> "JobResultResponse":
        return cls(
            srnum=record.srnum,
            result=record.result,
            complete_date=record.complete_date,
        )


@router.get("/jobs/{idx}/result", response_model=JobResultResponse)
async def get_job_result(request: Request, idx: int) -> JobResultResponse:
    database_path = request.app.state.database_path
    job = get_job_by_idx(database_path, idx)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    result = get_job_result_by_srnum(database_path, job.srnum)
    if result is None and int(job.job_type) == JOB_TYPE_WORKFLOW:
        try:
            result = ensure_workflow_job_result(database_path, job)
        except Exception:
            logger.exception("workflow job result backfill failed job=%s", job.idx)
    if result is None:
        raise HTTPException(status_code=404, detail="Job result not found")
    return JobResultResponse.from_record(result)


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _build_job_report_markdown(job: JobRecord, result: JobResultRecord) -> str:
    return build_job_result_report_markdown(
        job_title=job.job_title,
        srnum=job.srnum,
        complete_date=result.complete_date,
        result_body=result.result,
    )


def _build_rejected_job_markdown(job: JobRecord) -> str:
    reason = (job.reject_reason or job.drop_reason or "").strip() or "반려 사유가 등록되지 않았습니다."
    content = _strip_html(job.job_content)
    return (
        f"# {job.job_title}\n\n"
        f"- SR 번호: {job.srnum}\n"
        f"- 요청 일시: {job.request_date}\n"
        f"- 상태: 반려\n\n"
        f"## 작업 내용\n\n{content}\n\n"
        f"## 반려 사유\n\n{reason}\n"
    )


async def _notify_ax_infra_reject_or_cancel(database_path, job: JobRecord) -> None:
    if int(job.job_type) != JOB_TYPE_AX_INFRA:
        return
    try:
        if job.status_code == JOB_STATUS_REJECTED:
            reason = (job.reject_reason or job.drop_reason or "").strip()
            await send_ax_infra_job_rejection_email(
                database_path=database_path,
                job_title=job.job_title,
                requester_email=job.requester_email,
                approver_userid=job.approver,
                reject_reason=reason,
            )
        elif job.status_code == JOB_STATUS_CANCELLED:
            await send_ax_infra_job_cancellation_email(
                database_path=database_path,
                job_title=job.job_title,
                requester_email=job.requester_email,
                approver_userid=job.approver,
                drop_reason=(job.drop_reason or "").strip(),
            )
    except Exception:
        logger.exception(
            "AX infra reject/cancel email notification failed for idx=%s srnum=%s status=%s",
            job.idx,
            job.srnum,
            job.status_code,
        )


def _build_job_email_markdown(job: JobRecord, result: JobResultRecord | None) -> str | None:
    if result is not None:
        return _build_job_report_markdown(job, result)
    if job.status_code == JOB_STATUS_REJECTED:
        return _build_rejected_job_markdown(job)
    return None


@router.post("/jobs/{idx}/send-report-email", response_model=SendMarkdownEmailResponse)
async def send_job_report_email(
    request: Request,
    idx: int,
    body: SendEmailRecipientsRequest,
) -> SendMarkdownEmailResponse:
    get_request_auth_user(request)
    database_path = request.app.state.database_path

    job = get_job_by_idx(database_path, idx)
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    if job.job_type == JOB_TYPE_SIGNUP:
        raise HTTPException(status_code=400, detail="이 작업 유형은 메일로 전송할 수 없습니다.")

    result = get_job_result_by_srnum(database_path, job.srnum)
    report_body = _build_job_email_markdown(job, result)
    if report_body is None:
        raise HTTPException(status_code=404, detail="메일로 전송할 작업 내용이 없습니다.")

    try:
        resolved = resolve_email_recipients(
            database_path,
            body,
            requester_email=job.requester_email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    email_subject = (body.subject or "").strip() or job.job_title.strip()
    markdown_body = compose_report_markdown(
        forward_message=body.forward_message,
        report_body=report_body,
    )
    try:
        sent_count, failed = await send_job_report_emails(
            database_path=database_path,
            to_addresses=resolved.to_addresses,
            cc_addresses=resolved.cc_addresses,
            bcc_addresses=resolved.bcc_addresses,
            subject=email_subject,
            markdown_body=markdown_body,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Job report email send failed for job=%s", idx)
        raise HTTPException(status_code=502, detail="메일 전송에 실패했습니다.") from exc

    if sent_count == 0:
        raise HTTPException(
            status_code=502,
            detail=f"메일 전송에 실패했습니다: {', '.join(failed)}",
        )

    message = "메일을 전송했습니다."
    if sent_count > 0:
        parts = [f"수신 {len(resolved.to_addresses)}"]
        if resolved.cc_addresses:
            parts.append(f"참조 {len(resolved.cc_addresses)}")
        if resolved.bcc_addresses:
            parts.append(f"숨은참조 {len(resolved.bcc_addresses)}")
        message = f"메일을 전송했습니다 ({', '.join(parts)})."
    if failed:
        message = f"{message} (실패: {', '.join(failed)})"
    return SendMarkdownEmailResponse(
        sent_count=sent_count,
        failed_recipients=failed,
        message=message,
    )


class AssignJobApproverRequest(BaseModel):
    approver: str = Field(min_length=1, max_length=20)


@router.post("/jobs/{idx}/approver", response_model=JobRecordResponse)
async def assign_job_approver_endpoint(
    request: Request,
    idx: int,
    body: AssignJobApproverRequest,
) -> JobRecordResponse:
    database_path = request.app.state.database_path
    try:
        record = assign_job_approver(database_path, idx, approver_userid=body.approver)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Job approver assignment failed")
        raise HTTPException(status_code=500, detail="Failed to assign job approver") from exc
    return JobRecordResponse.from_record(record)


class DirectApproveJobRequest(BaseModel):
    actor_userid: str = Field(min_length=1, max_length=20)


@router.post("/jobs/{idx}/direct-approve", response_model=JobRecordResponse)
async def direct_approve_job_endpoint(
    request: Request,
    idx: int,
    body: DirectApproveJobRequest,
) -> JobRecordResponse:
    database_path = request.app.state.database_path
    try:
        record = direct_approve_job(database_path, idx, approver_userid=body.actor_userid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Job direct approve failed")
        raise HTTPException(status_code=500, detail="Failed to direct approve job") from exc
    await _notify_signup_job_approved(database_path, record)
    await _resume_workflow_job_if_needed(request, record)
    return JobRecordResponse.from_record(record)


class JobReviewActionRequest(BaseModel):
    actor_userid: str = Field(min_length=1, max_length=20)


class JobRejectRequest(JobReviewActionRequest):
    drop_reason: str = Field(min_length=1, max_length=200)


class JobCancelRequest(JobReviewActionRequest):
    drop_reason: str = Field(min_length=1, max_length=200)


@router.post("/jobs/{idx}/approve", response_model=JobRecordResponse)
async def approve_job_review(
    request: Request,
    idx: int,
    body: JobReviewActionRequest,
) -> JobRecordResponse:
    database_path = request.app.state.database_path
    try:
        record = approve_assigned_job(database_path, idx, actor_userid=body.actor_userid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Job approve failed")
        raise HTTPException(status_code=500, detail="Failed to approve job") from exc
    await _notify_signup_job_approved(database_path, record)
    await _resume_workflow_job_if_needed(request, record)
    return JobRecordResponse.from_record(record)


@router.post("/jobs/{idx}/reject", response_model=JobRecordResponse)
async def reject_job_review(
    request: Request,
    idx: int,
    body: JobRejectRequest,
) -> JobRecordResponse:
    database_path = request.app.state.database_path
    existing = get_job_by_idx(database_path, idx)
    if existing is None:
        raise HTTPException(status_code=404, detail="Job not found")

    try:
        if existing.status_code == JOB_STATUS_RECEIVED:
            record = reject_received_job(
                database_path,
                idx,
                actor_userid=body.actor_userid,
                drop_reason=body.drop_reason,
            )
        elif existing.status_code == JOB_STATUS_APPROVER_ASSIGNED:
            record = reject_assigned_job(
                database_path,
                idx,
                actor_userid=body.actor_userid,
                drop_reason=body.drop_reason,
            )
        else:
            raise HTTPException(status_code=400, detail="반려할 수 없는 작업 상태입니다.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Job reject failed")
        raise HTTPException(status_code=500, detail="Failed to reject job") from exc
    _fail_workflow_job_if_needed(database_path, record)
    await _notify_ax_infra_reject_or_cancel(database_path, record)
    return JobRecordResponse.from_record(record)


def _ensure_job_ai_review_access(job: JobRecord, viewer_userid: str, viewer_role: int) -> None:
    if job.job_type == JOB_TYPE_SIGNUP and _hide_signup_jobs_for_viewer(viewer_role):
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status_code == JOB_STATUS_RECEIVED:
        if not is_admin_role(viewer_role):
            raise HTTPException(status_code=403, detail="접수 작업 AI 검토는 관리자만 수행할 수 있습니다.")
        return

    if job.status_code == JOB_STATUS_APPROVER_ASSIGNED:
        approver = (job.approver or "").strip()
        if is_admin_role(viewer_role) or viewer_userid == approver:
            return
        raise HTTPException(status_code=403, detail="지정된 승인자 또는 관리자만 AI 검토할 수 있습니다.")

    raise HTTPException(status_code=400, detail="현재 상태에서는 AI 검토를 수행할 수 없습니다.")


class JobAiReviewResponse(BaseModel):
    ai_audit_comment: str
    ai_audit_date: str | None = None
    ai_audit_cnt: int = 0


@router.post("/jobs/{idx}/ai-review", response_model=JobAiReviewResponse)
async def ai_review_job(
    request: Request,
    idx: int,
) -> JobAiReviewResponse:
    database_path = request.app.state.database_path
    viewer = get_request_auth_user(request)
    job = get_job_by_idx(database_path, idx)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    _ensure_job_ai_review_access(job, viewer.userid, viewer.role)

    runtime_mode = getattr(request.app.state, "agent_runtime_mode", "mock")
    agent_runtime = request.app.state.agent_runtime
    agent_manager = request.app.state.agent_manager
    control_plane_base_url = getattr(request.app.state, "control_plane_base_url", None)

    try:
        auditor_agent_id = resolve_job_auditor_agent_id(database_path, runtime_mode)
        auditor_runtime_record = try_resolve_job_auditor_runtime_record(
            database_path,
            runtime_mode,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    message = build_job_review_message(job)
    review_task_id = f"job-ai-review-{job.idx}"

    if agent_manager is not None:
        agent_manager.mark_agent_working(
            auditor_agent_id,
            f"AI 검토: {job.srnum}",
            task_id=review_task_id,
        )

    try:
        result = await agent_runtime.invoke(
            AgentInvokeRequest(
                agent_id=auditor_agent_id,
                message=message,
                trace_id=uuid4().hex,
                control_plane_base_url=control_plane_base_url,
                agentruntime_idx=(
                    auditor_runtime_record.idx if auditor_runtime_record is not None else None
                ),
            )
        )
    except Exception as exc:
        logger.exception("Job AI review failed for idx=%s srnum=%s", job.idx, job.srnum)
        raise HTTPException(status_code=500, detail=f"AI 검토 요청에 실패했습니다: {exc}") from exc
    finally:
        if agent_manager is not None:
            agent_manager.mark_agent_idle(auditor_agent_id, task_id=review_task_id)

    try:
        updated_job = update_job_ai_audit_comment(
            database_path,
            job.idx,
            result.content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to persist AI audit comment for idx=%s", job.idx)
        raise HTTPException(status_code=500, detail="AI 검토 결과 저장에 실패했습니다.") from exc

    return JobAiReviewResponse(
        ai_audit_comment=updated_job.ai_audit_comment,
        ai_audit_date=updated_job.ai_audit_date,
        ai_audit_cnt=updated_job.ai_audit_cnt,
    )


@router.post("/jobs/{idx}/rework", response_model=JobRecordResponse)
async def rework_job_endpoint(
    request: Request,
    idx: int,
    body: JobReviewActionRequest,
) -> JobRecordResponse:
    database_path = request.app.state.database_path
    try:
        record = rework_job(database_path, idx, actor_userid=body.actor_userid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Job rework failed")
        raise HTTPException(status_code=500, detail="Failed to rework job") from exc
    return JobRecordResponse.from_record(record)


@router.post("/jobs/{idx}/cancel", response_model=JobRecordResponse)
async def cancel_job_endpoint(
    request: Request,
    idx: int,
    body: JobCancelRequest,
) -> JobRecordResponse:
    database_path = request.app.state.database_path
    try:
        record = cancel_failed_job(
            database_path,
            idx,
            actor_userid=body.actor_userid,
            drop_reason=body.drop_reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Job cancel failed")
        raise HTTPException(status_code=500, detail="Failed to cancel job") from exc
    await _notify_ax_infra_reject_or_cancel(database_path, record)
    return JobRecordResponse.from_record(record)
