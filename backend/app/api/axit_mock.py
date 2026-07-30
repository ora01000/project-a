"""Local AXIT platform mock APIs (token + agent invoke)."""

from __future__ import annotations

import base64
import logging
import secrets
import time
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.db.agentruntime import get_agentruntime_by_agent_id, resolve_local_agent_id
from backend.app.services.agent_invocation import invoke_agent_by_id
from backend.app.services.axit_config import (
    AXIT_ACCESS_TOKEN_TTL_SECONDS,
    resolve_axit_client_id,
    resolve_axit_client_secret,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["axit-mock"])

_issued_tokens: dict[str, float] = {}


class AxitInvokeRequest(BaseModel):
    service_id: str = Field(min_length=1, max_length=20)
    session_id: str = Field(min_length=1, max_length=100)
    session_attributes: dict[str, Any] = Field(default_factory=dict)
    prompt_session_attributes: dict[str, Any] = Field(default_factory=dict)
    enable_trace: bool = False
    text: str = Field(min_length=1)


class AxitInvokeResponse(BaseModel):
    text: str
    retrieval_results: list[Any] = Field(default_factory=list)
    trace: list[Any] = Field(default_factory=list)


def _decode_basic_credentials(authorization: str) -> tuple[str, str]:
    if not authorization.startswith("Basic "):
        raise HTTPException(status_code=401, detail="Basic authentication required")
    try:
        decoded = base64.b64decode(authorization[6:].strip()).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid Basic credentials") from exc
    if ":" not in decoded:
        raise HTTPException(status_code=401, detail="Invalid Basic credentials")
    client_id, client_secret = decoded.split(":", 1)
    return client_id, client_secret


def _purge_expired_tokens(now: float) -> None:
    expired = [token for token, expires_at in _issued_tokens.items() if expires_at <= now]
    for token in expired:
        _issued_tokens.pop(token, None)


def _require_bearer_token(request: Request) -> str:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization[7:].strip()
    now = time.time()
    _purge_expired_tokens(now)
    expires_at = _issued_tokens.get(token)
    if expires_at is None or expires_at <= now:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")
    return token


async def _invoke_axit_agent(agent_id: str, payload: AxitInvokeRequest, request: Request) -> AxitInvokeResponse:
    _require_bearer_token(request)

    database_path = request.app.state.database_path
    runtime_record = get_agentruntime_by_agent_id(database_path, agent_id, runtime_mode="mock")
    if runtime_record is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    if payload.service_id != runtime_record.service_id:
        raise HTTPException(
            status_code=400,
            detail=f"service_id mismatch (expected {runtime_record.service_id})",
        )

    local_agent_id = resolve_local_agent_id(database_path, agent_id, runtime_mode="mock")
    if local_agent_id is None:
        raise HTTPException(status_code=404, detail="Local agent mapping not found")

    manager = request.app.state.agent_manager
    if local_agent_id not in manager.agents:
        raise HTTPException(status_code=404, detail=f"Local agent '{local_agent_id}' not found")

    manager.mark_agent_working(local_agent_id, "AXIT invoke")
    try:
        result = await invoke_agent_by_id(manager, local_agent_id, payload.text)
    except Exception as exc:
        manager.mark_agent_error(local_agent_id, str(exc), input_message=payload.text)
        logger.exception("AXIT mock invoke failed for %s: %s", agent_id, exc)
        raise HTTPException(status_code=502, detail=f"Agent invoke failed: {exc}") from exc
    finally:
        manager.mark_agent_idle(local_agent_id)

    trace_payload: list[Any] = []
    if payload.enable_trace:
        trace_payload = [
            {
                "agent_id": agent_id,
                "local_agent_id": local_agent_id,
                "tools": [
                    {"name": tool.name, "mcp_server": tool.mcp_server}
                    for tool in result.tools_used
                ],
            },
        ]

    return AxitInvokeResponse(
        text=result.content,
        retrieval_results=[],
        trace=trace_payload,
    )


@router.post("/portal/auths/v1/token")
async def issue_access_token(
    request: Request,
    grant_type: str = Form(...),
) -> dict[str, str | int]:
    if grant_type != "client_credentials":
        raise HTTPException(status_code=400, detail="Unsupported grant_type")

    client_id, client_secret = _decode_basic_credentials(request.headers.get("Authorization", ""))
    expected_id = resolve_axit_client_id(runtime_mode="mock")
    expected_secret = resolve_axit_client_secret(runtime_mode="mock")
    if client_id != expected_id or client_secret != expected_secret:
        raise HTTPException(status_code=401, detail="Invalid client credentials")

    access_token = secrets.token_urlsafe(32)
    now = time.time()
    _purge_expired_tokens(now)
    _issued_tokens[access_token] = now + AXIT_ACCESS_TOKEN_TTL_SECONDS
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": AXIT_ACCESS_TOKEN_TTL_SECONDS,
    }


@router.post("/aihub/agents/v1/{agent_id}", response_model=AxitInvokeResponse)
async def invoke_axit_agent(agent_id: str, payload: AxitInvokeRequest, request: Request) -> AxitInvokeResponse:
    return await _invoke_axit_agent(agent_id, payload, request)


@router.post("/aihub/agents/v1/{agent_id}/invoke", response_model=AxitInvokeResponse)
async def invoke_axit_agent_with_suffix(
    agent_id: str,
    payload: AxitInvokeRequest,
    request: Request,
) -> AxitInvokeResponse:
    return await _invoke_axit_agent(agent_id, payload, request)
