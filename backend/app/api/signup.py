from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.db.signup_notifications import list_signup_notifications_for_user
from backend.app.services.user_signup import (
    approve_signup,
    dismiss_signup_notification,
    register_pending_user,
    reject_signup,
)

router = APIRouter(tags=["signup"])


class RegisterUserRequest(BaseModel):
    userid: str = Field(min_length=1, max_length=50)
    email: str = Field(min_length=1, max_length=50)
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=50)
    depart: str = Field(min_length=1, max_length=100)


class RegisterUserResponse(BaseModel):
    message: str


class SignupNotificationResponse(BaseModel):
    idx: int
    user_idx: int
    title: str
    message: str
    created_at: str


class RejectSignupRequest(BaseModel):
    reason: str = Field(min_length=1)


@router.post("/auth/register", response_model=RegisterUserResponse, status_code=201)
async def register_user(payload: RegisterUserRequest, request: Request) -> RegisterUserResponse:
    import sqlite3

    database_path = request.app.state.database_path
    try:
        register_pending_user(
            database_path,
            userid=payload.userid,
            email=payload.email,
            username=payload.username,
            password=payload.password,
            depart=payload.depart,
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다.") from exc

    return RegisterUserResponse(
        message="가입 신청이 접수되었습니다. 관리자 승인 후 로그인할 수 있습니다.",
    )


@router.get("/signup/notifications/{target_user}", response_model=list[SignupNotificationResponse])
async def get_signup_notifications(target_user: str, request: Request) -> list[SignupNotificationResponse]:
    database_path = request.app.state.database_path
    notifications = list_signup_notifications_for_user(database_path, target_user)
    return [
        SignupNotificationResponse(
            idx=notification.idx,
            user_idx=notification.user_idx,
            title=notification.title,
            message=notification.message,
            created_at=notification.created_at,
        )
        for notification in notifications
    ]


@router.post("/signup/notifications/{notification_idx}/dismiss")
async def dismiss_notification(notification_idx: int, request: Request) -> dict[str, bool]:
    database_path = request.app.state.database_path
    deleted = dismiss_signup_notification(database_path, notification_idx)
    if not deleted:
        raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다.")
    return {"deleted": True}


@router.post("/signup/users/{user_idx}/approve")
async def approve_signup_user(user_idx: int, request: Request) -> dict[str, str]:
    database_path = request.app.state.database_path
    try:
        updated = approve_signup(database_path, user_idx)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
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
