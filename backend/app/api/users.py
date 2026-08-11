from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.db.assignable_agents import known_assignable_agent_ids
from backend.app.db.engine import is_integrity_error
from backend.app.db.roles import is_admin_role, is_hidden_system_user
from backend.app.db.users import (
    User,
    create_user,
    delete_users,
    encode_agent_ids,
    get_user_by_idx,
    list_users,
    parse_agent_ids,
    replace_whatap_event_subscribers,
    update_user,
    update_user_agents,
)
from backend.app.middleware.session_auth import get_request_auth_user

router = APIRouter(tags=["users"])


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
    request_reason: str = ""
    last_login: str | None = None
    whatap_event_sub: bool = False

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
            request_reason=user.request_reason,
            last_login=user.last_login,
            whatap_event_sub=user.whatap_event_sub,
        )


class CreateUserRequest(BaseModel):
    userid: str = Field(min_length=1, max_length=50)
    email: str = Field(min_length=1, max_length=50)
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=50)
    depart: str = Field(min_length=1, max_length=100)
    role: int = Field(ge=0, le=5)
    band: int = Field(default=1, ge=1, le=3)
    viewer_role: int


class UpdateUserRequest(BaseModel):
    email: str = Field(min_length=1, max_length=50)
    username: str = Field(min_length=1, max_length=50)
    password: str | None = Field(default=None, max_length=50)
    depart: str = Field(min_length=1, max_length=100)
    role: int = Field(ge=0, le=5)
    band: int = Field(default=1, ge=1, le=3)
    viewer_role: int


class DeleteUsersRequest(BaseModel):
    idx_list: list[int] = Field(min_length=1)
    viewer_role: int


class UserAgentAssignmentItem(BaseModel):
    idx: int
    agent_ids: list[str] = Field(default_factory=list)


class SaveUserAgentAssignmentsRequest(BaseModel):
    assignments: list[UserAgentAssignmentItem] = Field(min_length=1)


class SaveUserAgentAssignmentsResponse(BaseModel):
    updated: int
    users: list[UserResponse]


def _validate_agent_ids(request: Request, agent_ids: list[str]) -> list[str]:
    database_path = request.app.state.database_path
    runtime_mode = getattr(request.app.state, "agent_runtime_mode", "mock")
    normalized = parse_agent_ids(",".join(agent_ids))
    known = known_assignable_agent_ids(database_path, runtime_mode=runtime_mode)
    unknown = [agent_id for agent_id in normalized if agent_id not in known]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"알 수 없는 에이전트 ID: {', '.join(unknown)}",
        )
    try:
        encode_agent_ids(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return normalized


def _require_admin(viewer_role: int) -> None:
    if not is_admin_role(viewer_role):
        raise HTTPException(status_code=403, detail="관리자만 수행할 수 있습니다.")


@router.get("/users", response_model=list[UserResponse])
async def get_users(request: Request, viewer_role: int | None = None) -> list[UserResponse]:
    database_path = request.app.state.database_path
    return [UserResponse.from_user(user) for user in list_users(database_path, viewer_role=viewer_role)]


@router.post("/users", response_model=UserResponse, status_code=201)
async def add_user(payload: CreateUserRequest, request: Request) -> UserResponse:
    _require_admin(payload.viewer_role)
    if is_hidden_system_user(payload.userid.strip()):
        raise HTTPException(status_code=400, detail="사용할 수 없는 아이디입니다.")
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
            band=payload.band,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        if is_integrity_error(exc):
            raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다.") from exc
        raise

    return UserResponse.from_user(user)


@router.put("/users/agent-assignments", response_model=SaveUserAgentAssignmentsResponse)
async def save_user_agent_assignments(
    payload: SaveUserAgentAssignmentsRequest,
    request: Request,
) -> SaveUserAgentAssignmentsResponse:
    database_path = request.app.state.database_path
    updated_users: list[User] = []

    for item in payload.assignments:
        existing = get_user_by_idx(database_path, item.idx)
        if existing is None:
            raise HTTPException(status_code=404, detail=f"사용자를 찾을 수 없습니다: idx={item.idx}")
        if is_hidden_system_user(existing.userid, existing.role):
            raise HTTPException(status_code=404, detail=f"사용자를 찾을 수 없습니다: idx={item.idx}")
        agent_ids = _validate_agent_ids(request, item.agent_ids)
        updated = update_user_agents(database_path, item.idx, agent_ids)
        if updated is None:
            raise HTTPException(status_code=404, detail=f"사용자를 찾을 수 없습니다: idx={item.idx}")
        updated_users.append(updated)

    return SaveUserAgentAssignmentsResponse(
        updated=len(updated_users),
        users=[UserResponse.from_user(user) for user in updated_users],
    )


@router.put("/users/{idx}", response_model=UserResponse)
async def modify_user(idx: int, payload: UpdateUserRequest, request: Request) -> UserResponse:
    _require_admin(payload.viewer_role)
    database_path = request.app.state.database_path
    existing = get_user_by_idx(database_path, idx)
    if existing is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    if is_hidden_system_user(existing.userid, existing.role):
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
        band=payload.band,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return UserResponse.from_user(updated)


@router.delete("/users")
async def remove_users(
    request: Request,
    payload: DeleteUsersRequest = Body(...),
) -> dict[str, int]:
    _require_admin(payload.viewer_role)
    database_path = request.app.state.database_path
    deleted_count = delete_users(database_path, payload.idx_list)
    return {"deleted": deleted_count}


class WhatapEventSubscriptionResponse(BaseModel):
    event_type: str = "Whatap Event"
    userids: list[str] = Field(default_factory=list)


class WhatapEventSubscriptionUpdateRequest(BaseModel):
    userids: list[str] = Field(default_factory=list)


@router.get(
    "/admin/whatap-event-subscriptions",
    response_model=WhatapEventSubscriptionResponse,
)
async def get_whatap_event_subscriptions(request: Request) -> WhatapEventSubscriptionResponse:
    viewer = get_request_auth_user(request)
    _require_admin(viewer.role)
    subscribers = [
        user.userid
        for user in list_users(request.app.state.database_path, viewer_role=viewer.role)
        if user.whatap_event_sub
    ]
    return WhatapEventSubscriptionResponse(userids=subscribers)


@router.put(
    "/admin/whatap-event-subscriptions",
    response_model=WhatapEventSubscriptionResponse,
)
async def put_whatap_event_subscriptions(
    payload: WhatapEventSubscriptionUpdateRequest,
    request: Request,
) -> WhatapEventSubscriptionResponse:
    viewer = get_request_auth_user(request)
    _require_admin(viewer.role)
    database_path = request.app.state.database_path

    validated: list[str] = []
    known_users = {
        user.userid: user
        for user in list_users(database_path, viewer_role=viewer.role)
    }
    for raw in payload.userids:
        userid = str(raw or "").strip()
        if not userid:
            continue
        if userid not in known_users:
            raise HTTPException(status_code=400, detail=f"존재하지 않는 사용자입니다: {userid}")
        if is_hidden_system_user(userid, known_users[userid].role):
            raise HTTPException(status_code=400, detail=f"사용할 수 없는 사용자입니다: {userid}")
        validated.append(userid)

    subscribers = replace_whatap_event_subscribers(database_path, validated)
    return WhatapEventSubscriptionResponse(userids=[user.userid for user in subscribers])
