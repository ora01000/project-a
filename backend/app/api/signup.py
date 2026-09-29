from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
import logging

from backend.app.services.auth_provider import MADANG_EMAIL_DOMAINS
from backend.app.notifications.email_sender import send_signup_request_admin_emails
from backend.app.services.user_signup import (
    approve_signup,
    notify_signup_approved,
    register_pending_user,
    reject_signup,
)

router = APIRouter(tags=["signup"])
logger = logging.getLogger(__name__)


class RegisterUserRequest(BaseModel):
    userid: str = Field(min_length=1, max_length=50)
    email_local: str = Field(min_length=1, max_length=40)
    email_domain: str = Field(min_length=1, max_length=40)
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=50)
    depart: str = Field(min_length=1, max_length=100)
    request_reason: str = Field(min_length=1, max_length=200)
    band: int = Field(default=1, ge=1, le=3)


class RegisterUserResponse(BaseModel):
    message: str


class RejectSignupRequest(BaseModel):
    reason: str = Field(min_length=1)


@router.post("/auth/register", response_model=RegisterUserResponse, status_code=201)
async def register_user(payload: RegisterUserRequest, request: Request) -> RegisterUserResponse:
    from backend.app.db.engine import is_integrity_error

    email_domain = payload.email_domain.strip()
    if email_domain not in MADANG_EMAIL_DOMAINS:
        raise HTTPException(status_code=400, detail="허용되지 않은 이메일 도메인입니다.")

    email_local = payload.email_local.strip()
    if "@" in email_local:
        raise HTTPException(status_code=400, detail="이메일 아이디만 입력해 주세요.")

    email = f"{email_local}{email_domain}"
    database_path = request.app.state.database_path
    try:
        _user, job = register_pending_user(
            database_path,
            userid=payload.userid.strip(),
            email=email,
            username=payload.username.strip(),
            password=payload.password,
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

    return RegisterUserResponse(
        message="가입 신청이 접수되었습니다. 관리자 승인 후 로그인할 수 있습니다.",
    )


@router.post("/signup/users/{user_idx}/approve")
async def approve_signup_user(user_idx: int, request: Request) -> dict[str, str]:
    database_path = request.app.state.database_path
    try:
        updated = approve_signup(database_path, user_idx)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    await notify_signup_approved(database_path, updated)
    return {"status": "approved", "userid": updated.userid}


@router.post("/signup/users/{user_idx}/reject")
async def reject_signup_user(
    user_idx: int,
    payload: RejectSignupRequest,
    request: Request,
) -> dict[str, str]:
    database_path = request.app.state.database_path
    try:
        rejected = await reject_signup(database_path, user_idx, payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not rejected:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return {"status": "rejected"}
