from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.config import load_auth_provider_settings
from backend.app.db.users import User, get_user_by_idx, update_user
from backend.app.services.auth_provider import AuthProviderError, login_with_provider

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


class LoginResponse(UserResponse):
    profile_required: bool = False


class AuthProviderResponse(BaseModel):
    provider_type: str
    registration_enabled: bool


class CompleteProfileRequest(BaseModel):
    idx: int
    email: str = Field(min_length=1, max_length=50)
    username: str = Field(min_length=1, max_length=50)
    depart: str = Field(min_length=1, max_length=100)
    password: str | None = Field(default=None, max_length=50)


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

    base = UserResponse.from_user(result.user)
    return LoginResponse(**base.model_dump(), profile_required=result.profile_required)


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
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return UserResponse.from_user(updated)
