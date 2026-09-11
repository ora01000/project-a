import json
import logging
from datetime import date
from typing import AsyncIterator
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from backend.app.agents.mock_platform_agents import WORKFLOW_AGENT_LOCAL_AGENT_ID
from backend.app.agents.base import AgentInvokeResult, ToolUsage
from backend.app.db.roles import is_admin_role
from backend.app.db.users import parse_agent_ids
from backend.app.disabled_features import is_removed_agent_id, raise_disabled_feature
from backend.app.logging.agent_logger import log_agent_interaction
from backend.app.logging.user_comm_logger import list_user_communications, log_user_communication
from backend.app.logging.workflow_logger import log_workflow_agent_interaction
from backend.app.middleware.session_auth import get_request_auth_user
from backend.app.services.agent_runtime_client import AgentInvokeRequest
from backend.app.services.axit_platform_client import format_axit_invoke_error
from backend.app.services.chat_input_history_store import (
    append_chat_input_history,
    get_chat_input_history,
)

router = APIRouter(tags=["chat"])

logger = logging.getLogger(__name__)

# Feature terminals may expose these without user agent assignment.
_CHAT_WITHOUT_ASSIGNMENT_AGENT_IDS = frozenset({WORKFLOW_AGENT_LOCAL_AGENT_ID})


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    userid: str | None = Field(default=None, max_length=50)
    session_id: str | None = Field(default=None, max_length=100)
    # WORKFLOW_AGENT: prefer real workflow uuid; create flow may omit (session used).
    workflow_uuid: str | None = Field(default=None, max_length=64)


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


class ChatInputHistoryResponse(BaseModel):
    agent_id: str
    messages: list[str]


class ChatInputHistoryAppendRequest(BaseModel):
    message: str = Field(min_length=1)


def _ensure_chat_agent_access(request: Request, agent_id: str) -> None:
    manager = request.app.state.agent_manager
    if agent_id not in manager.agents:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    if agent_id in _CHAT_WITHOUT_ASSIGNMENT_AGENT_IDS:
        return

    user = get_request_auth_user(request)
    allowed = set(parse_agent_ids(user.agents))
    if agent_id not in allowed:
        raise HTTPException(status_code=403, detail="할당되지 않은 에이전트입니다.")


@router.get("/chat/input-history/{agent_id}", response_model=ChatInputHistoryResponse)
async def get_chat_input_history_endpoint(agent_id: str, request: Request) -> ChatInputHistoryResponse:
    if is_removed_agent_id(agent_id):
        raise_disabled_feature()

    _ensure_chat_agent_access(request, agent_id)
    user = get_request_auth_user(request)
    messages = await get_chat_input_history(user.userid, agent_id)
    return ChatInputHistoryResponse(agent_id=agent_id, messages=messages)


@router.post("/chat/input-history/{agent_id}", response_model=ChatInputHistoryResponse)
async def append_chat_input_history_endpoint(
    agent_id: str,
    payload: ChatInputHistoryAppendRequest,
    request: Request,
) -> ChatInputHistoryResponse:
    if is_removed_agent_id(agent_id):
        raise_disabled_feature()

    _ensure_chat_agent_access(request, agent_id)
    user = get_request_auth_user(request)
    messages = await append_chat_input_history(user.userid, agent_id, payload.message)
    return ChatInputHistoryResponse(agent_id=agent_id, messages=messages)


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


async def _invoke_agent(
    request: Request,
    agent_id: str,
    message: str,
    *,
    session_id: str | None = None,
) -> AgentInvokeResult:
    return await request.app.state.agent_runtime.invoke(
        AgentInvokeRequest(
            agent_id=agent_id,
            message=message,
            session_id=session_id,
            trace_id=uuid4().hex,
            control_plane_base_url=getattr(request.app.state, "control_plane_base_url", None),
        ),
    )


@router.post("/agents/{agent_id}/chat")
async def chat_with_agent(agent_id: str, payload: ChatRequest, request: Request):
    if is_removed_agent_id(agent_id):
        raise_disabled_feature()

    manager = request.app.state.agent_manager

    if agent_id not in manager.agents:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    auth_user = get_request_auth_user(request)
    if payload.userid and payload.userid.strip() != auth_user.userid:
        raise HTTPException(status_code=403, detail="요청 사용자와 세션 사용자가 일치하지 않습니다.")

    if agent_id not in _CHAT_WITHOUT_ASSIGNMENT_AGENT_IDS:
        allowed = set(parse_agent_ids(auth_user.agents))
        if agent_id not in allowed:
            raise HTTPException(status_code=403, detail="할당되지 않은 에이전트입니다.")

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        chat_task_id = manager.mark_agent_working(agent_id, "채팅 응답", task_id=uuid4().hex)
        try:
            result = await _invoke_agent(
                request,
                agent_id,
                payload.message,
                session_id=payload.session_id,
            )
            async for event in _stream_response(result):
                yield event

            if agent_id == WORKFLOW_AGENT_LOCAL_AGENT_ID:
                workflow_key = (
                    (payload.workflow_uuid or "").strip()
                    or (payload.session_id or "").strip()
                    or "unknown"
                )
                log_workflow_agent_interaction(
                    userid=auth_user.userid,
                    workflow_key=workflow_key,
                    agent_id=agent_id,
                    input_message=payload.message,
                    output_message=result.content,
                    tools_used=result.tools_used,
                    user_name=auth_user.username,
                )
            else:
                log_agent_interaction(
                    agent_id=agent_id,
                    input_message=payload.message,
                    output_message=result.content,
                    tools_used=result.tools_used,
                    user_id=auth_user.userid,
                    user_name=auth_user.username,
                )

                try:
                    definition = manager.get_definition(agent_id)
                    log_user_communication(
                        auth_user.userid,
                        agent_id=agent_id,
                        agent_name=definition.name,
                        user_message=payload.message,
                        assistant_message=result.content,
                        tools_used=result.tools_used,
                    )
                except ValueError as exc:
                    logger.warning("Skipped user comm log for %s: %s", auth_user.userid, exc)
        except Exception as exc:
            error_message = format_axit_invoke_error(exc)
            manager.mark_agent_error(agent_id, error_message, input_message=payload.message)
            yield {
                "event": "error",
                "data": json.dumps({"message": error_message}),
            }
            return
        finally:
            manager.mark_agent_idle(agent_id, chat_task_id)

    return EventSourceResponse(event_generator())


@router.get("/chat/logs/{userid}", response_model=UserCommLogResponse)
async def get_user_chat_logs(
    userid: str,
    request: Request,
    log_date: str | None = Query(default=None, alias="date"),
) -> UserCommLogResponse:
    viewer = get_request_auth_user(request)
    normalized_userid = userid.strip()
    if normalized_userid != viewer.userid and not is_admin_role(viewer.role):
        raise HTTPException(status_code=403, detail="다른 사용자의 로그를 조회할 수 없습니다.")

    try:
        target_date = date.fromisoformat(log_date) if log_date else None
        payload = list_user_communications(normalized_userid, log_date=target_date)
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
        and str(entry.get("agent_id") or "").strip() != WORKFLOW_AGENT_LOCAL_AGENT_ID
    ]

    return UserCommLogResponse(
        user_id=str(payload.get("user_id", userid)),
        date=str(payload.get("date", "")),
        entries=entries,
    )
