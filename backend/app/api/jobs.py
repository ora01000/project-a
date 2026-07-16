import json
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.app.agents.system_agents import NotifyChannel
from backend.app.db.job_datetime import now_job_datetime
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
    restore_job_plan,
    save_job_plan_edit,
)
from backend.app.db.notifications import delete_job_notification, list_notifications_for_user
from backend.app.services.job_execution import (
    JobExecutionConflictError,
    JobExecutionNotAllowedError,
    accept_and_schedule_job_execution,
    hold_job,
    mark_job_under_review,
    reject_job,
)
from backend.app.services.job_planning import submit_job_request
from backend.app.testing.job_request_samples import (
    REQUEST_DEPART,
    REQUESTER,
    REQUESTER_EMAIL,
    get_job_request_sample,
    list_job_request_samples,
)

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
    original_job_plan: dict | None = None
    execution_result: dict | None = None
    actual_completion_time: str | None = None

    @classmethod
    def from_job(cls, job: Job) -> "JobResponse":
        def _parse_plan(raw: str | None) -> dict | None:
            if not raw:
                return None
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"summary": raw, "steps": []}

        job_plan = _parse_plan(job.job_plan)
        original_job_plan = _parse_plan(job.original_job_plan)
        execution_result = None
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
            original_job_plan=original_job_plan,
            execution_result=execution_result,
            actual_completion_time=job.actual_completion_time,
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


class JobPlanStepPayload(BaseModel):
    agent_id: str = Field(min_length=1)
    agent_name: str | None = None
    tool_name: str | None = None
    tool_params: dict | None = None
    description: str | None = None


class JobPlanUpdateRequest(BaseModel):
    summary: str = ""
    steps: list[JobPlanStepPayload] = Field(default_factory=list)


class JobTestSampleResponse(BaseModel):
    sample_id: str
    job_title: str
    job_description: str
    request_depart: str
    requester: str
    requester_email: str
    approver: str
    target_agent_family: str
    notes: str


class SendJobTestSampleRequest(BaseModel):
    sample_id: str = Field(min_length=1)
    job_title: str = Field(min_length=1, max_length=200)
    job_description: str = Field(min_length=1)
    request_depart: str = Field(min_length=1, max_length=50)
    requester: str = Field(min_length=1, max_length=50)
    approver: str = Field(min_length=1, max_length=50)
    requester_email: str | None = Field(default=None, max_length=50)
    notify_channel: NotifyChannel = NotifyChannel.INTEGRATED_CHAT


REQUESTER_EMAIL_BY_NAME = {
    "윤인수": "isyun@lguplus.co.kr",
    "안세훈": "loadan@lguplus.co.kr",
}


def _resolve_requester_email(requester: str, requester_email: str | None) -> str:
    if requester_email and requester_email.strip():
        return requester_email.strip()
    return REQUESTER_EMAIL_BY_NAME.get(requester.strip(), REQUESTER_EMAIL)


@router.get("/jobs/test-samples", response_model=list[JobTestSampleResponse])
async def get_job_test_samples() -> list[JobTestSampleResponse]:
    return [
        JobTestSampleResponse(
            sample_id=sample.sample_id,
            job_title=sample.job_title,
            job_description=sample.job_description,
            request_depart=REQUEST_DEPART,
            requester=REQUESTER,
            requester_email=REQUESTER_EMAIL,
            approver=sample.approver,
            target_agent_family=sample.target_agent_family,
            notes=sample.notes,
        )
        for sample in list_job_request_samples()
    ]


@router.post("/jobs/test-samples/send", response_model=JobResponse, status_code=201)
async def send_job_test_sample(payload: SendJobTestSampleRequest, request: Request) -> JobResponse:
    sample = get_job_request_sample(payload.sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="테스트 샘플을 찾을 수 없습니다.")

    database_path = request.app.state.database_path
    request_date = now_job_datetime()
    completion_request_date = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
    job = await submit_job_request(
        database_path,
        request_date=request_date,
        job_title=payload.job_title,
        request_depart=payload.request_depart,
        requester=payload.requester,
        requester_email=_resolve_requester_email(payload.requester, payload.requester_email),
        completion_request_date=completion_request_date,
        job_description=payload.job_description,
        approver=payload.approver,
        notify_channel=payload.notify_channel,
        agent_manager=request.app.state.agent_manager,
    )
    return JobResponse.from_job(job)


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
        agent_manager=request.app.state.agent_manager,
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


@router.post("/jobs/notifications/{notification_idx}/dismiss")
async def dismiss_job_notification(notification_idx: int, request: Request) -> dict[str, bool]:
    database_path = request.app.state.database_path
    deleted = delete_job_notification(database_path, notification_idx)
    if not deleted:
        raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다.")
    return {"ok": True}


@router.get("/jobs/{idx}", response_model=JobResponse)
async def get_job(idx: int, request: Request) -> JobResponse:
    from backend.app.db.jobs import get_job_by_idx

    database_path = request.app.state.database_path
    job = get_job_by_idx(database_path, idx)
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return JobResponse.from_job(job)


@router.put("/jobs/{idx}/plan", response_model=JobResponse)
async def update_job_plan_endpoint(idx: int, payload: JobPlanUpdateRequest, request: Request) -> JobResponse:
    from backend.app.db.jobs import get_job_by_idx

    database_path = request.app.state.database_path
    job = get_job_by_idx(database_path, idx)
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    if job.state not in {JOB_STATE_PLAN_COMPLETED, JOB_STATE_UNDER_REVIEW, JOB_STATE_PENDING}:
        raise HTTPException(status_code=400, detail="현재 상태에서는 작업 계획을 수정할 수 없습니다.")

    plan_json = json.dumps(
        {
            "summary": payload.summary,
            "steps": [step.model_dump() for step in payload.steps],
        },
        ensure_ascii=False,
    )
    updated = save_job_plan_edit(database_path, idx, plan_json)
    if updated is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return JobResponse.from_job(updated)


@router.post("/jobs/{idx}/plan/restore", response_model=JobResponse)
async def restore_job_plan_endpoint(idx: int, request: Request) -> JobResponse:
    from backend.app.db.jobs import get_job_by_idx

    database_path = request.app.state.database_path
    job = get_job_by_idx(database_path, idx)
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    if job.state not in {JOB_STATE_PLAN_COMPLETED, JOB_STATE_UNDER_REVIEW, JOB_STATE_PENDING}:
        raise HTTPException(status_code=400, detail="현재 상태에서는 작업 계획을 원복할 수 없습니다.")

    updated = restore_job_plan(database_path, idx)
    if updated is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return JobResponse.from_job(updated)


@router.post("/jobs/{idx}/actions/review", response_model=JobResponse)
async def review_job(idx: int, request: Request) -> JobResponse:
    database_path = request.app.state.database_path
    job = await mark_job_under_review(database_path, idx)
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return JobResponse.from_job(job)


@router.post("/jobs/{idx}/actions/approve", response_model=JobResponse, status_code=202)
async def approve_job(idx: int, request: Request) -> JobResponse:
    database_path = request.app.state.database_path
    manager = request.app.state.agent_manager
    try:
        job = await accept_and_schedule_job_execution(database_path, idx, manager, is_retry=False)
    except JobExecutionNotAllowedError as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from exc
    except JobExecutionConflictError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return JobResponse.from_job(job)


@router.post("/jobs/{idx}/actions/retry", response_model=JobResponse, status_code=202)
async def retry_job(idx: int, request: Request) -> JobResponse:
    database_path = request.app.state.database_path
    manager = request.app.state.agent_manager
    try:
        job = await accept_and_schedule_job_execution(database_path, idx, manager, is_retry=True)
    except JobExecutionNotAllowedError as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from exc
    except JobExecutionConflictError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
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
