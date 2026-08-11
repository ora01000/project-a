from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.config import load_auth_provider_settings, load_auth_session_settings
from backend.app.db.notice_board import list_welcome_notices
from backend.app.db.roles import ROLE_ADMIN, ROLE_PENDING
from backend.app.db.users import (
    User,
    build_userid_username_map,
    get_user_by_idx,
    get_user_by_userid,
    parse_agent_ids,
    record_user_login,
    resolve_username,
    update_user,
)
from backend.app.middleware.session_auth import extract_bearer_token, get_request_auth_user
from backend.app.services.auth_provider import (
    AuthProviderError,
    MADANG_EMAIL_DOMAINS,
    login_with_provider,
    verify_madang_credentials,
)
from backend.app.services.auth_session import create_session, revoke_session
from backend.app.services.madang_admin_bypass import (
    MADANG_ADMIN_BYPASS_USERID,
    verify_admin_bypass_passkey,
)
from backend.app.services.user_signup import register_pending_user
from backend.app.notifications.email_sender import send_signup_request_admin_emails

router = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)


class LoginRequest(BaseModel):
    userid: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=50)


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
    access_token: str | None = None
    token_type: str = "Bearer"
    expires_in: int | None = None
    profile_required: bool = False
    registration_required: bool = False
    welcome_back: bool = False
    previous_last_login: str | None = None
    welcome_notices: list[WelcomeNoticeSummary] = Field(default_factory=list)


class AuthProviderResponse(BaseModel):
    provider_type: str
    registration_enabled: bool
    madang_auth: bool = False


class MadangRegisterRequest(BaseModel):
    userid: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=50)
    email_local: str = Field(min_length=1, max_length=40)
    email_domain: str = Field(min_length=1, max_length=40)
    username: str = Field(min_length=1, max_length=50)
    depart: str = Field(min_length=1, max_length=100)
    request_reason: str = Field(min_length=1, max_length=200)
    band: int = Field(default=1, ge=1, le=3)


class MadangRegisterResponse(BaseModel):
    message: str


class MadangAdminBypassRequest(BaseModel):
    passkey: str = Field(min_length=1, max_length=64)


class MeResponse(UserResponse):
    expires_in: int


class CompleteProfileRequest(BaseModel):
    idx: int
    email: str = Field(min_length=1, max_length=50)
    username: str = Field(min_length=1, max_length=50)
    depart: str = Field(min_length=1, max_length=100)
    password: str | None = Field(default=None, max_length=50)
    band: int = Field(default=1, ge=1, le=3)


class LogoutResponse(BaseModel):
    ok: bool = True


@router.get("/auth/provider", response_model=AuthProviderResponse)
async def get_auth_provider() -> AuthProviderResponse:
    settings = load_auth_provider_settings()
    is_madang = settings.provider_type == "madang"
    return AuthProviderResponse(
        provider_type=settings.provider_type,
        registration_enabled=settings.provider_type == "db",
        madang_auth=is_madang,
    )


async def _issue_login_response(
    request: Request,
    user: User,
    *,
    profile_required: bool,
    welcome_back: bool = False,
    previous_last_login: str | None = None,
    welcome_notices: list[WelcomeNoticeSummary] | None = None,
) -> LoginResponse:
    session_settings = load_auth_session_settings()
    access_token, expires_in = await create_session(
        user.idx,
        user.userid,
        ttl_seconds=session_settings.ttl_seconds,
    )
    base = UserResponse.from_user(user)
    return LoginResponse(
        **base.model_dump(),
        access_token=access_token,
        expires_in=expires_in,
        profile_required=profile_required,
        welcome_back=welcome_back,
        previous_last_login=previous_last_login,
        welcome_notices=welcome_notices or [],
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

    if result.registration_required:
        return LoginResponse(
            idx=0,
            userid=result.userid,
            email="",
            username="",
            depart="",
            role=0,
            registration_required=True,
        )

    if result.user is None:
        raise HTTPException(status_code=500, detail="로그인 처리 중 오류가 발생했습니다.")

    previous_last_login, updated_user = record_user_login(database_path, result.user.idx)
    user = updated_user or result.user
    welcome_back = previous_last_login is not None and not result.profile_required
    welcome_notices: list[WelcomeNoticeSummary] = []
    if welcome_back:
        username_by_key = build_userid_username_map(database_path)
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

    return await _issue_login_response(
        request,
        user,
        profile_required=result.profile_required,
        welcome_back=welcome_back,
        previous_last_login=previous_last_login,
        welcome_notices=welcome_notices,
    )


@router.post("/auth/madang/admin-bypass", response_model=LoginResponse)
async def madang_admin_bypass_login(
    payload: MadangAdminBypassRequest,
    request: Request,
) -> LoginResponse:
    settings = load_auth_provider_settings()
    if settings.provider_type != "madang":
        raise HTTPException(status_code=400, detail="madang 인증 모드에서만 사용할 수 있습니다.")

    if not verify_admin_bypass_passkey(payload.passkey):
        raise HTTPException(status_code=401, detail="패스키가 올바르지 않습니다.")

    database_path = request.app.state.database_path

    target_user = get_user_by_userid(database_path, MADANG_ADMIN_BYPASS_USERID)
    if target_user is None:
        raise HTTPException(
            status_code=401,
            detail="관리자 우회 로그인에 실패했습니다. 지정 사용자를 찾을 수 없습니다.",
        )
    if target_user.role == ROLE_PENDING:
        raise HTTPException(
            status_code=403,
            detail="가입 승인 대기 중입니다. 관리자에게 문의해 주세요.",
        )

    previous_last_login, updated_user = record_user_login(database_path, target_user.idx)
    user = updated_user or target_user
    welcome_back = previous_last_login is not None
    welcome_notices: list[WelcomeNoticeSummary] = []
    if welcome_back:
        username_by_key = build_userid_username_map(database_path)
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

    return await _issue_login_response(
        request,
        user,
        profile_required=False,
        welcome_back=welcome_back,
        previous_last_login=previous_last_login,
        welcome_notices=welcome_notices,
    )


@router.post("/auth/madang/register", response_model=MadangRegisterResponse, status_code=201)
async def register_madang_user(payload: MadangRegisterRequest, request: Request) -> MadangRegisterResponse:
    from backend.app.db.engine import is_integrity_error

    settings = load_auth_provider_settings()
    if settings.provider_type != "madang":
        raise HTTPException(status_code=400, detail="madang 인증 모드에서만 사용할 수 있습니다.")

    email_domain = payload.email_domain.strip()
    if email_domain not in MADANG_EMAIL_DOMAINS:
        raise HTTPException(status_code=400, detail="허용되지 않은 이메일 도메인입니다.")

    email_local = payload.email_local.strip()
    if "@" in email_local:
        raise HTTPException(status_code=400, detail="이메일 아이디만 입력해 주세요.")

    email = f"{email_local}{email_domain}"
    normalized_userid = payload.userid.strip()
    database_path = request.app.state.database_path

    try:
        is_valid = await verify_madang_credentials(
            settings=settings,
            userid=normalized_userid,
            password=payload.password,
        )
    except AuthProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    if not is_valid:
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")

    if get_user_by_userid(database_path, normalized_userid) is not None:
        raise HTTPException(status_code=409, detail="이미 등록된 사용자입니다.")

    try:
        _user, job = register_pending_user(
            database_path,
            userid=normalized_userid,
            email=email,
            username=payload.username.strip(),
            password="",
            depart=payload.depart.strip(),
            band=payload.band,
            request_reason=payload.request_reason.strip(),
        )
    except Exception as exc:
        if is_integrity_error(exc):
            raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다.") from exc
        raise

    try:
        await send_signup_request_admin_emails(
            database_path=database_path,
            job_title=job.job_title,
            srnum=job.srnum,
            requester_name=job.requester_name,
            request_reason=job.job_content or payload.request_reason.strip(),
        )
    except Exception:
        logger.exception(
            "Signup request admin email failed for srnum=%s userid=%s",
            job.srnum,
            job.madang_id,
        )

    return MadangRegisterResponse(
        message="가입 신청이 접수되었습니다. 관리자 승인 후 로그인할 수 있습니다.",
    )


@router.get("/auth/me", response_model=MeResponse)
async def get_current_user(request: Request) -> MeResponse:
    user = get_request_auth_user(request)
    session_settings = load_auth_session_settings()
    return MeResponse(
        **UserResponse.from_user(user).model_dump(),
        expires_in=session_settings.ttl_seconds,
    )


@router.post("/auth/logout", response_model=LogoutResponse)
async def logout(request: Request) -> LogoutResponse:
    token = extract_bearer_token(request) or getattr(request.state, "auth_token", None)
    if token:
        await revoke_session(token)
    return LogoutResponse()


@router.put("/auth/profile", response_model=UserResponse)
async def complete_profile(payload: CompleteProfileRequest, request: Request) -> UserResponse:
    auth_user = get_request_auth_user(request)
    if auth_user.idx != payload.idx:
        raise HTTPException(status_code=403, detail="본인 프로필만 수정할 수 있습니다.")

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
