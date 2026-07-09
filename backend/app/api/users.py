import sqlite3

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.db.users import (
    User,
    create_user,
    delete_users,
    get_user_by_idx,
    list_users,
    update_user,
)

router = APIRouter(tags=["users"])


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


class CreateUserRequest(BaseModel):
    userid: str = Field(min_length=1, max_length=50)
    email: str = Field(min_length=1, max_length=50)
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=50)
    depart: str = Field(min_length=1, max_length=100)
    role: int = Field(ge=0, le=1)


class UpdateUserRequest(BaseModel):
    email: str = Field(min_length=1, max_length=50)
    username: str = Field(min_length=1, max_length=50)
    password: str | None = Field(default=None, max_length=50)
    depart: str = Field(min_length=1, max_length=100)
    role: int = Field(ge=0, le=1)


class DeleteUsersRequest(BaseModel):
    idx_list: list[int] = Field(min_length=1)


@router.get("/users", response_model=list[UserResponse])
async def get_users(request: Request) -> list[UserResponse]:
    database_path = request.app.state.database_path
    return [UserResponse.from_user(user) for user in list_users(database_path)]


@router.post("/users", response_model=UserResponse, status_code=201)
async def add_user(payload: CreateUserRequest, request: Request) -> UserResponse:
    database_path = request.app.state.database_path
    try:
        user = create_user(
            database_path,
            userid=payload.userid,
            email=payload.email,
            username=payload.username,
            password=payload.password,
            depart=payload.depart,
            role=payload.role,
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다.") from exc

    return UserResponse.from_user(user)


@router.put("/users/{idx}", response_model=UserResponse)
async def modify_user(idx: int, payload: UpdateUserRequest, request: Request) -> UserResponse:
    database_path = request.app.state.database_path
    existing = get_user_by_idx(database_path, idx)
    if existing is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    password = payload.password.strip() if payload.password else None
    updated = update_user(
        database_path,
        idx,
        email=payload.email,
        username=payload.username,
        password=password,
        depart=payload.depart,
        role=payload.role,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return UserResponse.from_user(updated)


@router.delete("/users")
async def remove_users(
    request: Request,
    payload: DeleteUsersRequest = Body(...),
) -> dict[str, int]:
    database_path = request.app.state.database_path
    deleted_count = delete_users(database_path, payload.idx_list)
    return {"deleted": deleted_count}
