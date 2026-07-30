"""AXIT agentruntime registry API."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.db.agentruntime import (
    AGENTRUNTIME_TYPE_EXTERNAL,
    AGENTRUNTIME_TYPE_MOCKUP,
    StoredAgentRuntime,
    create_agentruntime_record,
    delete_agentruntime_record,
    get_agentruntime_by_idx,
    list_agentruntime_records,
    resolve_active_agentruntime_type,
    update_agentruntime_record,
)
from backend.app.db.roles import ROLE_ADMIN

router = APIRouter(tags=["agentruntime"])


class AgentRuntimeRecordResponse(BaseModel):
    idx: int
    type: int
    agent_name: str
    agent_id: str
    local_agent_id: str
    description: str
    registered_date: str
    service_id: str

    @classmethod
    def from_record(cls, record: StoredAgentRuntime) -> "AgentRuntimeRecordResponse":
        return cls(
            idx=record.idx,
            type=record.type,
            agent_name=record.agent_name,
            agent_id=record.agent_id,
            local_agent_id=record.local_agent_id,
            description=record.description,
            registered_date=record.registered_date,
            service_id=record.service_id,
        )


class AgentRuntimeWriteBody(BaseModel):
    type: int = Field(ge=0, le=1)
    agent_name: str = Field(min_length=1, max_length=50)
    agent_id: str = Field(min_length=1, max_length=50)
    local_agent_id: str = Field(default="", max_length=50)
    description: str = Field(default="", max_length=255)
    registered_date: str = Field(default="", max_length=40)
    service_id: str = Field(min_length=1, max_length=20)
    viewer_role: int


def _normalize_runtime_type(value: int) -> int:
    if value not in (AGENTRUNTIME_TYPE_MOCKUP, AGENTRUNTIME_TYPE_EXTERNAL):
        raise HTTPException(status_code=400, detail="type은 0(목업) 또는 1(외부연동)만 허용됩니다.")
    return value


def _require_admin(viewer_role: int) -> None:
    if viewer_role != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="관리자만 수행할 수 있습니다.")


def _active_runtime_mode(request: Request) -> str:
    return getattr(request.app.state, "agent_runtime_mode", "mock")


@router.get("/agentruntime", response_model=list[AgentRuntimeRecordResponse])
async def list_agentruntime(request: Request) -> list[AgentRuntimeRecordResponse]:
    database_path = request.app.state.database_path
    runtime_mode = _active_runtime_mode(request)
    return [
        AgentRuntimeRecordResponse.from_record(record)
        for record in list_agentruntime_records(database_path, runtime_mode=runtime_mode)
    ]


@router.post("/agentruntime", response_model=AgentRuntimeRecordResponse)
async def create_agentruntime(
    request: Request,
    payload: AgentRuntimeWriteBody,
) -> AgentRuntimeRecordResponse:
    _require_admin(payload.viewer_role)
    database_path = request.app.state.database_path
    runtime_type = _normalize_runtime_type(payload.type)
    try:
        record = create_agentruntime_record(
            database_path,
            runtime_type=runtime_type,
            agent_name=payload.agent_name,
            agent_id=payload.agent_id,
            local_agent_id=payload.local_agent_id,
            description=payload.description,
            service_id=payload.service_id,
            registered_date=payload.registered_date or None,
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="동일한 type·agent_id 조합이 이미 존재합니다.",
        ) from exc
    return AgentRuntimeRecordResponse.from_record(record)


@router.put("/agentruntime/{idx}", response_model=AgentRuntimeRecordResponse)
async def update_agentruntime(
    idx: int,
    request: Request,
    payload: AgentRuntimeWriteBody,
) -> AgentRuntimeRecordResponse:
    _require_admin(payload.viewer_role)
    database_path = request.app.state.database_path
    existing = get_agentruntime_by_idx(database_path, idx)
    if existing is None:
        raise HTTPException(status_code=404, detail="에이전트 연결 정보를 찾을 수 없습니다.")

    active_type = resolve_active_agentruntime_type(_active_runtime_mode(request))
    if existing.type != active_type:
        raise HTTPException(status_code=400, detail="현재 런타임 모드에서 수정할 수 없는 연결입니다.")

    try:
        record = update_agentruntime_record(
            database_path,
            idx,
            agent_name=payload.agent_name,
            agent_id=payload.agent_id,
            local_agent_id=payload.local_agent_id,
            description=payload.description,
            service_id=payload.service_id,
            registered_date=payload.registered_date or existing.registered_date,
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="동일한 type·agent_id 조합이 이미 존재합니다.",
        ) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="에이전트 연결 정보를 찾을 수 없습니다.")
    return AgentRuntimeRecordResponse.from_record(record)


class DeleteAgentRuntimeRequest(BaseModel):
    viewer_role: int


@router.delete("/agentruntime/{idx}")
async def delete_agentruntime(
    idx: int,
    request: Request,
    payload: DeleteAgentRuntimeRequest = Body(...),
) -> dict[str, bool]:
    _require_admin(payload.viewer_role)
    database_path = request.app.state.database_path
    existing = get_agentruntime_by_idx(database_path, idx)
    if existing is None:
        raise HTTPException(status_code=404, detail="에이전트 연결 정보를 찾을 수 없습니다.")

    active_type = resolve_active_agentruntime_type(_active_runtime_mode(request))
    if existing.type != active_type:
        raise HTTPException(status_code=400, detail="현재 런타임 모드에서 삭제할 수 없는 연결입니다.")

    if not delete_agentruntime_record(database_path, idx):
        raise HTTPException(status_code=404, detail="에이전트 연결 정보를 찾을 수 없습니다.")
    return {"deleted": True}
