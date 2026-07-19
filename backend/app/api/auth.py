from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.config import load_auth_provider_settings
from backend.app.db.jobs import Job, job_state_label, list_jobs_by_approver
from backend.app.db.notice_board import list_welcome_notices
from backend.app.db.users import (
    User,
    build_userid_username_map,
    get_user_by_idx,
    parse_agent_ids,
    record_user_login,
    resolve_username,
    update_user,
)
from backend.app.services.auth_provider import AuthProviderError, login_with_provider

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    userid: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=50)


class ApproverJobSummary(BaseModel):
    idx: int
    job_title: str
    request_date: str
    requester: str
    request_depart: str
    state: int
    state_label: str
    completion_request_date: str
    sr_num: str | None = None

    @classmethod
    def from_job(cls, job: Job, *, username_by_key: dict[str, str] | None = None) -> "ApproverJobSummary":
        requester = job.requester
        if username_by_key is not None:
            requester = resolve_username(job.requester, username_by_key)
        return cls(
            idx=job.idx,
            job_title=job.job_title,
            request_date=job.request_date,
            requester=requester,
            request_depart=job.request_depart,
            state=job.state,
            state_label=job_state_label(job.state),
            completion_request_date=job.completion_request_date,
            sr_num=job.sr_num,
        )


class WelcomeNoticeSummary(BaseModel):
    idx: int
    writer: str
    writer_name: str
    title: str
    from_date: str
    until_date: str
    notice: str


class UserResponse(BaseModel):
    idx: int
    userid: str
    email: str
    username: str
    depart: str
    role: int
    band: int = 1
    agents: str = ""
    agent_ids: list[str] = Field(default_factory=list)
    last_login: str | None = None

    @classmethod
    def from_user(cls, user: User) -> "UserResponse":
        agent_ids = parse_agent_ids(user.agents)
        return cls(
            idx=user.idx,
            userid=user.userid,
            email=user.email,
            username=user.username,
            depart=user.depart,
            role=user.role,
            band=user.band,
            agents=user.agents or "",
            agent_ids=agent_ids,
            last_login=user.last_login,
        )


class LoginResponse(UserResponse):
    profile_required: bool = False
    welcome_back: bool = False
    previous_last_login: str | None = None
    approver_jobs: list[ApproverJobSummary] = Field(default_factory=list)
    welcome_notices: list[WelcomeNoticeSummary] = Field(default_factory=list)


class AuthProviderResponse(BaseModel):
    provider_type: str
    registration_enabled: bool


class CompleteProfileRequest(BaseModel):
    idx: int
    email: str = Field(min_length=1, max_length=50)
    username: str = Field(min_length=1, max_length=50)
    depart: str = Field(min_length=1, max_length=100)
    password: str | None = Field(default=None, max_length=50)
    band: int = Field(default=1, ge=1, le=3)


@router.get("/auth/provider", response_model=AuthProviderResponse)
async def get_auth_provider() -> AuthProviderResponse:
    settings = load_auth_provider_settings()
    return AuthProviderResponse(
        provider_type=settings.provider_type,
        registration_enabled=settings.provider_type == "db",
    )


@router.post("/auth/login", response_model=LoginResponse)
async def login(payload: LoginRequest, request: Request) -> LoginResponse:
    database_path = request.app.state.database_path
    try:
        result = await login_with_provider(
            database_path,
            userid=payload.userid,
            password=payload.password,
        )
    except AuthProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    previous_last_login, updated_user = record_user_login(database_path, result.user.idx)
    user = updated_user or result.user
    welcome_back = previous_last_login is not None and not result.profile_required
    approver_jobs: list[ApproverJobSummary] = []
    welcome_notices: list[WelcomeNoticeSummary] = []
    if welcome_back:
        username_by_key = build_userid_username_map(database_path)
        jobs = list_jobs_by_approver(
            database_path,
            userid=user.userid,
            username=user.username,
        )
        approver_jobs = [
            ApproverJobSummary.from_job(job, username_by_key=username_by_key) for job in jobs
        ]
        welcome_notices = [
            WelcomeNoticeSummary(
                idx=notice.idx,
                writer=notice.writer,
                writer_name=resolve_username(notice.writer, username_by_key),
                title=notice.title,
                from_date=notice.from_date,
                until_date=notice.until_date,
                notice=notice.notice,
            )
            for notice in list_welcome_notices(database_path)
        ]

    base = UserResponse.from_user(user)
    return LoginResponse(
        **base.model_dump(),
        profile_required=result.profile_required,
        welcome_back=welcome_back,
        previous_last_login=previous_last_login,
        approver_jobs=approver_jobs,
        welcome_notices=welcome_notices,
    )


@router.put("/auth/profile", response_model=UserResponse)
async def complete_profile(payload: CompleteProfileRequest, request: Request) -> UserResponse:
    database_path = request.app.state.database_path
    existing = get_user_by_idx(database_path, payload.idx)
    if existing is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    updated = update_user(
        database_path,
        payload.idx,
        email=payload.email,
        username=payload.username,
        password=payload.password,
        depart=payload.depart,
        role=existing.role,
        band=payload.band,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return UserResponse.from_user(updated)
