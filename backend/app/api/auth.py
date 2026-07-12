from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.db.roles import ROLE_PENDING
from backend.app.db.users import User, authenticate_user

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    userid: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=50)


class UserResponse(BaseModel):
    idx: int
    userid: str
    email: str
    username: str
    depart: str
    role: int

    @classmethod
    def from_user(cls, user: User) -> "UserResponse":
        return cls(
            idx=user.idx,
            userid=user.userid,
            email=user.email,
            username=user.username,
            depart=user.depart,
            role=user.role,
        )


@router.post("/auth/login", response_model=UserResponse)
async def login(payload: LoginRequest, request: Request) -> UserResponse:
    database_path = request.app.state.database_path
    user = authenticate_user(database_path, payload.userid, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")
    if user.role == ROLE_PENDING:
        raise HTTPException(
            status_code=403,
            detail="가입 승인 대기 중입니다. 관리자에게 문의해 주세요.",
        )
    return UserResponse.from_user(user)
