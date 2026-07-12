import sqlite3

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.config import load_settings
from backend.app.db.agents import (
    StoredAgent,
    create_agent,
    delete_agents,
    get_stored_agent_by_idx,
    list_stored_agents,
    update_agent,
)

router = APIRouter(tags=["agent-records"])


class AgentRecordResponse(BaseModel):
    idx: int
    agent_id: str
    name: str
    role: str
    system_prompt: str
    mcp_server_keys: list[str]

    @classmethod
    def from_stored_agent(cls, agent: StoredAgent) -> "AgentRecordResponse":
        return cls(
            idx=agent.idx,
            agent_id=agent.agent_id,
            name=agent.name,
            role=agent.role,
            system_prompt=agent.system_prompt,
            mcp_server_keys=list(agent.mcp_server_keys),
        )


class CreateAgentRecordRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=50)
    role: str = Field(min_length=1, max_length=200)
    system_prompt: str = Field(min_length=1)
    mcp_server_keys: list[str] = Field(default_factory=list)


class UpdateAgentRecordRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=50)
    role: str = Field(min_length=1, max_length=200)
    system_prompt: str = Field(min_length=1)
    mcp_server_keys: list[str] = Field(default_factory=list)


class DeleteAgentRecordsRequest(BaseModel):
    idx_list: list[int] = Field(min_length=1)


class McpServerOptionResponse(BaseModel):
    key: str
    enabled: bool


async def _reload_runtime_agents(request: Request) -> None:
    manager = request.app.state.agent_manager
    await manager.reload_agents(request.app.state.database_path)


@router.get("/agent-records", response_model=list[AgentRecordResponse])
async def get_agent_records(request: Request) -> list[AgentRecordResponse]:
    database_path = request.app.state.database_path
    return [AgentRecordResponse.from_stored_agent(agent) for agent in list_stored_agents(database_path)]


@router.post("/agent-records", response_model=AgentRecordResponse, status_code=201)
async def add_agent_record(payload: CreateAgentRecordRequest, request: Request) -> AgentRecordResponse:
    database_path = request.app.state.database_path
    try:
        agent = create_agent(
            database_path,
            agent_id=payload.agent_id,
            name=payload.name,
            role=payload.role,
            system_prompt=payload.system_prompt,
            mcp_server_keys=payload.mcp_server_keys,
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="이미 사용 중인 에이전트 ID입니다.") from exc

    await _reload_runtime_agents(request)
    return AgentRecordResponse.from_stored_agent(agent)


@router.put("/agent-records/{idx}", response_model=AgentRecordResponse)
async def modify_agent_record(
    idx: int,
    payload: UpdateAgentRecordRequest,
    request: Request,
) -> AgentRecordResponse:
    database_path = request.app.state.database_path
    existing = get_stored_agent_by_idx(database_path, idx)
    if existing is None:
        raise HTTPException(status_code=404, detail="에이전트를 찾을 수 없습니다.")

    try:
        updated = update_agent(
            database_path,
            idx,
            agent_id=payload.agent_id,
            name=payload.name,
            role=payload.role,
            system_prompt=payload.system_prompt,
            mcp_server_keys=payload.mcp_server_keys,
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="이미 사용 중인 에이전트 ID입니다.") from exc

    if updated is None:
        raise HTTPException(status_code=404, detail="에이전트를 찾을 수 없습니다.")

    await _reload_runtime_agents(request)
    return AgentRecordResponse.from_stored_agent(updated)


@router.delete("/agent-records")
async def remove_agent_records(
    request: Request,
    payload: DeleteAgentRecordsRequest = Body(...),
) -> dict[str, int]:
    database_path = request.app.state.database_path
    deleted_count = delete_agents(database_path, payload.idx_list)
    await _reload_runtime_agents(request)
    return {"deleted": deleted_count}


@router.get("/mcp-servers", response_model=list[McpServerOptionResponse])
async def get_mcp_servers() -> list[McpServerOptionResponse]:
    _, _, mcp_servers, _ = load_settings()
    return [
        McpServerOptionResponse(key=key, enabled=config.enabled)
        for key, config in sorted(mcp_servers.items())
    ]
