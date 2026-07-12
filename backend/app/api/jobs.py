import json

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.app.agents.system_agents import NotifyChannel
from backend.app.db.jobs import (
    JOB_STATE_COMPLETED,
    JOB_STATE_PENDING,
    JOB_STATE_PLAN_COMPLETED,
    JOB_STATE_UNDER_REVIEW,
    Job,
    job_state_label,
    list_jobs,
    list_jobs_by_state,
    list_jobs_by_states,
)
from backend.app.db.notifications import list_notifications_for_user
from backend.app.services.job_execution import (
    execute_job,
    hold_job,
    mark_job_under_review,
    reject_job,
)
from backend.app.services.job_planning import submit_job_request

router = APIRouter(tags=["jobs"])


class JobRequestPayload(BaseModel):
    request_date: str = Field(min_length=1)
    job_title: str = Field(min_length=1, max_length=200)
    request_depart: str = Field(min_length=1, max_length=50)
    requester: str = Field(min_length=1, max_length=50)
    requester_email: str = Field(min_length=1, max_length=50)
    completion_request_date: str = Field(min_length=1)
    job_description: str = Field(min_length=1)
    approver: str = Field(min_length=1, max_length=50)
    notify_channel: NotifyChannel = NotifyChannel.INTEGRATED_CHAT


class JobResponse(BaseModel):
    idx: int
    request_date: str
    job_title: str
    request_depart: str
    requester: str
    requester_email: str
    completion_request_date: str
    job_description: str
    approver: str
    state: int
    state_label: str
    notify_channel: str
    job_plan: dict | None = None
    execution_result: dict | None = None

    @classmethod
    def from_job(cls, job: Job) -> "JobResponse":
        job_plan = None
        execution_result = None
        if job.job_plan:
            try:
                job_plan = json.loads(job.job_plan)
            except json.JSONDecodeError:
                job_plan = {"summary": job.job_plan, "steps": []}
        if job.execution_result:
            try:
                execution_result = json.loads(job.execution_result)
            except json.JSONDecodeError:
                execution_result = {"summary": job.execution_result, "results": []}

        return cls(
            idx=job.idx,
            request_date=job.request_date,
            job_title=job.job_title,
            request_depart=job.request_depart,
            requester=job.requester,
            requester_email=job.requester_email,
            completion_request_date=job.completion_request_date,
            job_description=job.job_description,
            approver=job.approver,
            state=job.state,
            state_label=job_state_label(job.state),
            notify_channel=job.notify_channel,
            job_plan=job_plan,
            execution_result=execution_result,
        )


class JobNotificationResponse(BaseModel):
    idx: int
    job_idx: int
    notification_type: str
    title: str
    message: str
    created_at: str


class RejectJobRequest(BaseModel):
    reason: str = ""


@router.post("/jobs", response_model=JobResponse, status_code=201)
async def create_job_request(payload: JobRequestPayload, request: Request) -> JobResponse:
    database_path = request.app.state.database_path
    job = await submit_job_request(
        database_path,
        request_date=payload.request_date,
        job_title=payload.job_title,
        request_depart=payload.request_depart,
        requester=payload.requester,
        requester_email=payload.requester_email,
        completion_request_date=payload.completion_request_date,
        job_description=payload.job_description,
        approver=payload.approver,
        notify_channel=payload.notify_channel,
    )
    return JobResponse.from_job(job)


@router.get("/jobs", response_model=list[JobResponse])
async def get_jobs(
    request: Request,
    state: int | None = Query(default=None),
) -> list[JobResponse]:
    database_path = request.app.state.database_path
    if state is None:
        jobs = list_jobs(database_path)
    else:
        jobs = list_jobs_by_state(database_path, state)
    return [JobResponse.from_job(job) for job in jobs]


@router.get("/jobs/review", response_model=list[JobResponse])
async def get_review_jobs(request: Request) -> list[JobResponse]:
    database_path = request.app.state.database_path
    jobs = list_jobs_by_states(
        database_path,
        [JOB_STATE_PLAN_COMPLETED, JOB_STATE_UNDER_REVIEW],
    )
    return [JobResponse.from_job(job) for job in jobs]


@router.get("/jobs/pending", response_model=list[JobResponse])
async def get_pending_jobs(request: Request) -> list[JobResponse]:
    database_path = request.app.state.database_path
    jobs = list_jobs_by_state(database_path, JOB_STATE_PENDING)
    return [JobResponse.from_job(job) for job in jobs]


@router.get("/jobs/completed", response_model=list[JobResponse])
async def get_completed_jobs(request: Request) -> list[JobResponse]:
    database_path = request.app.state.database_path
    jobs = list_jobs_by_state(database_path, JOB_STATE_COMPLETED)
    return [JobResponse.from_job(job) for job in jobs]


@router.get("/jobs/notifications/{target_user}", response_model=list[JobNotificationResponse])
async def get_job_notifications(target_user: str, request: Request) -> list[JobNotificationResponse]:
    database_path = request.app.state.database_path
    notifications = list_notifications_for_user(database_path, target_user)
    return [
        JobNotificationResponse(
            idx=notification.idx,
            job_idx=notification.job_idx,
            notification_type=notification.notification_type,
            title=notification.title,
            message=notification.message,
            created_at=notification.created_at,
        )
        for notification in notifications
    ]


@router.get("/jobs/{idx}", response_model=JobResponse)
async def get_job(idx: int, request: Request) -> JobResponse:
    from backend.app.db.jobs import get_job_by_idx

    database_path = request.app.state.database_path
    job = get_job_by_idx(database_path, idx)
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return JobResponse.from_job(job)


@router.post("/jobs/{idx}/actions/review", response_model=JobResponse)
async def review_job(idx: int, request: Request) -> JobResponse:
    database_path = request.app.state.database_path
    job = await mark_job_under_review(database_path, idx)
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return JobResponse.from_job(job)


@router.post("/jobs/{idx}/actions/approve", response_model=JobResponse)
async def approve_job(idx: int, request: Request) -> JobResponse:
    database_path = request.app.state.database_path
    manager = request.app.state.agent_manager
    job = await execute_job(database_path, idx, manager)
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return JobResponse.from_job(job)


@router.post("/jobs/{idx}/actions/pending", response_model=JobResponse)
async def pending_job(idx: int, request: Request) -> JobResponse:
    database_path = request.app.state.database_path
    job = await hold_job(database_path, idx)
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return JobResponse.from_job(job)


@router.post("/jobs/{idx}/actions/reject", response_model=JobResponse)
async def reject_job_action(idx: int, payload: RejectJobRequest, request: Request) -> JobResponse:
    database_path = request.app.state.database_path
    job = await reject_job(database_path, idx, payload.reason)
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return JobResponse.from_job(job)
