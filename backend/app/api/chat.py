import json
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from backend.app.agents.base import AgentInvokeResult, ToolUsage, invoke_agent
from backend.app.logging.agent_logger import log_agent_interaction

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


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


async def _stream_text_only(text: str) -> AsyncIterator[dict[str, str]]:
    chunk_size = 80
    for index in range(0, len(text), chunk_size):
        chunk = text[index : index + chunk_size]
        yield {"event": "token", "data": json.dumps({"content": chunk})}
    yield {"event": "done", "data": json.dumps({"content": "", "tools": []})}


def _build_mcp_disabled_message(mcp_server_keys: list[str]) -> str:
    env_hints = ", ".join(f"MCP_{key.upper()}_ENABLED=true" for key in mcp_server_keys)
    yaml_hints = ", ".join(f"{key}.enabled=true" for key in mcp_server_keys)
    return (
        "연결된 MCP 서버가 없습니다. "
        f"환경변수({env_hints}) 또는 config/mcp_servers.yaml({yaml_hints})에서 "
        "활성화 및 endpoint URL을 설정한 뒤 백엔드를 재시작해 주세요."
    )


@router.post("/agents/{agent_id}/chat")
async def chat_with_agent(agent_id: str, payload: ChatRequest, request: Request):
    manager = request.app.state.agent_manager

    if agent_id not in manager.agents:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    agent = manager.get_agent(agent_id)
    definition = manager.get_definition(agent_id)
    mcp_statuses = {
        key: manager.mcp_manager.connection_status.get(key, "unknown")
        for key in definition.mcp_server_keys
    }

    if mcp_statuses and all(status == "disabled" for status in mcp_statuses.values()):
        disabled_message = _build_mcp_disabled_message(definition.mcp_server_keys)
        log_agent_interaction(
            agent_id=agent_id,
            input_message=payload.message,
            output_message=disabled_message,
            tools_used=[],
        )
        return EventSourceResponse(_stream_text_only(disabled_message))

    try:
        result = await invoke_agent(agent, payload.message, manager.mcp_manager)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    log_agent_interaction(
        agent_id=agent_id,
        input_message=payload.message,
        output_message=result.content,
        tools_used=result.tools_used,
    )

    return EventSourceResponse(_stream_response(result))
