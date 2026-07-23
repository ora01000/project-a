import json
import logging
from datetime import date
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from backend.app.agents.base import (
    AgentInvokeResult,
    ToolUsage,
)
from backend.app.agents.system_agents import is_chat_enabled_system_agent_id
from backend.app.db.users import get_user_by_userid, parse_agent_ids
from backend.app.logging.agent_logger import log_agent_interaction
from backend.app.logging.user_comm_logger import list_user_communications, log_user_communication
from backend.app.services.agent_invocation import invoke_agent_by_id

router = APIRouter(tags=["chat"])

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    userid: str | None = Field(default=None, max_length=50)


class UserCommLogEntry(BaseModel):
    timestamp: str
    agent_id: str
    agent_name: str
    user_message: str
    assistant_message: str
    tools: list[dict[str, str | None]]


class UserCommLogResponse(BaseModel):
    user_id: str
    date: str
    entries: list[UserCommLogEntry]


def _serialize_tools(tools_used: list[ToolUsage]) -> list[dict[str, str | None]]:
    return [
        {"name": tool.name, "mcp_server": tool.mcp_server}
        for tool in tools_used
    ]


async def _stream_response(result: AgentInvokeResult) -> AsyncIterator[dict[str, str]]:
    yield {
        "event": "tools",
        "data": json.dumps({"tools": _serialize_tools(result.tools_used)}),
    }

    chunk_size = 80
    for index in range(0, len(result.content), chunk_size):
        chunk = result.content[index : index + chunk_size]
        yield {"event": "token", "data": json.dumps({"content": chunk})}

    yield {
        "event": "done",
        "data": json.dumps({"content": "", "tools": _serialize_tools(result.tools_used)}),
    }


@router.post("/agents/{agent_id}/chat")
async def chat_with_agent(agent_id: str, payload: ChatRequest, request: Request):
    manager = request.app.state.agent_manager

    if agent_id not in manager.agents:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    if payload.userid and not is_chat_enabled_system_agent_id(agent_id):
        user = get_user_by_userid(request.app.state.database_path, payload.userid)
        if user is None:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
        allowed = set(parse_agent_ids(user.agents))
        if agent_id not in allowed:
            raise HTTPException(status_code=403, detail="할당되지 않은 에이전트입니다.")

    manager.mark_agent_working(agent_id, "채팅 응답")
    try:
        result = await invoke_agent_by_id(manager, agent_id, payload.message)
    except Exception as exc:
        manager.mark_agent_error(agent_id, str(exc), input_message=payload.message)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    log_agent_interaction(
        agent_id=agent_id,
        input_message=payload.message,
        output_message=result.content,
        tools_used=result.tools_used,
    )

    if payload.userid:
        try:
            definition = manager.get_definition(agent_id)
            log_user_communication(
                payload.userid,
                agent_id=agent_id,
                agent_name=definition.name,
                user_message=payload.message,
                assistant_message=result.content,
                tools_used=result.tools_used,
            )
        except ValueError as exc:
            logger.warning("Skipped user comm log for %s: %s", payload.userid, exc)

    manager.mark_agent_idle(agent_id)
    return EventSourceResponse(_stream_response(result))


@router.get("/chat/logs/{userid}", response_model=UserCommLogResponse)
async def get_user_chat_logs(
    userid: str,
    log_date: str | None = Query(default=None, alias="date"),
) -> UserCommLogResponse:
    try:
        target_date = date.fromisoformat(log_date) if log_date else None
        payload = list_user_communications(userid, log_date=target_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    entries = [
        UserCommLogEntry(
            timestamp=str(entry.get("timestamp", "")),
            agent_id=str(entry.get("agent_id", "")),
            agent_name=str(entry.get("agent_name", "")),
            user_message=str(entry.get("user_message", "")),
            assistant_message=str(entry.get("assistant_message", "")),
            tools=entry.get("tools", []) if isinstance(entry.get("tools"), list) else [],
        )
        for entry in payload.get("entries", [])
        if isinstance(entry, dict)
    ]

    return UserCommLogResponse(
        user_id=str(payload.get("user_id", userid)),
        date=str(payload.get("date", "")),
        entries=entries,
    )
