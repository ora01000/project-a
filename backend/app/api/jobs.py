"""Job request intake API (Teams / Power Automate inbound)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.app.db.jobs import (
    JOB_STATUS_APPROVER_ASSIGNED,
    JOB_STATUS_RECEIVED,
    JOB_TYPE_SIGNUP,
    JobRecord,
    approve_assigned_job,
    assign_job_approver,
    cancel_failed_job,
    direct_approve_job,
    get_job_by_idx,
    list_jobs,
    reject_assigned_job,
    reject_received_job,
    rework_job,
)
from backend.app.db.jobs_result import JobResultRecord, get_job_result_by_srnum
from backend.app.db.roles import is_admin_role
from backend.app.middleware.session_auth import get_request_auth_user
from backend.app.services.job_intake import receive_job_request

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jobs"])


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
    exclude_status_code: int | None = Query(default=None),
) -> list[JobRecordResponse]:
    database_path = request.app.state.database_path
    viewer = get_request_auth_user(request)
    records = list_jobs(
        database_path,
        status_code=status_code,
        min_status_code=min_status_code,
        approver=approver,
        exclude_status_code=exclude_status_code,
        exclude_job_type=JOB_TYPE_SIGNUP if _hide_signup_jobs_for_viewer(viewer.role) else None,
    )
    return [JobRecordResponse.from_record(record) for record in records]


@router.get("/jobs/{idx}", response_model=JobRecordResponse)
async def get_job_record(request: Request, idx: int) -> JobRecordResponse:
    database_path = request.app.state.database_path
    viewer = get_request_auth_user(request)
    record = get_job_by_idx(database_path, idx)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if record.job_type == JOB_TYPE_SIGNUP and _hide_signup_jobs_for_viewer(viewer.role):
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
    if result is None:
        raise HTTPException(status_code=404, detail="Job result not found")
    return JobResultResponse.from_record(result)


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
    return JobRecordResponse.from_record(record)


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
    return JobRecordResponse.from_record(record)
