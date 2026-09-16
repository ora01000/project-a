"""API for standalone INFRA_SEARCH_AGENT."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.infra_search_agent.agent import infra_search_agent_service
from backend.app.infra_search_agent.settings import STATIC_CONFIG
from backend.app.logging.agent_logger import log_agent_error, log_agent_interaction
from backend.app.middleware.session_auth import get_request_auth_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["infra-search-agent"])


class InfraSearchInvokeRequest(BaseModel):
    message: str = Field(min_length=1)


class InfraSearchInvokeResponse(BaseModel):
    agent_id: str
    content: str
    tools_used: list[dict[str, str | None]]
    input_tokens: int = 0
    output_tokens: int = 0


@router.get("/infra-search-agent/status")
async def infra_search_agent_status() -> dict:
    return infra_search_agent_service.status()


@router.post("/infra-search-agent/invoke", response_model=InfraSearchInvokeResponse)
async def infra_search_agent_invoke(
    body: InfraSearchInvokeRequest,
    request: Request,
) -> InfraSearchInvokeResponse:
    auth_user = get_request_auth_user(request)
    try:
        result = await infra_search_agent_service.invoke(body.message.strip())
    except Exception as exc:
        logger.exception("INFRA_SEARCH_AGENT invoke failed")
        log_agent_error(
            STATIC_CONFIG.agent_id,
            reason=str(exc),
            input_message=body.message,
            user_id=auth_user.userid,
            user_name=auth_user.username,
        )
        raise HTTPException(
            status_code=500,
            detail=f"INFRA_SEARCH_AGENT invoke failed: {exc}",
        ) from exc

    log_agent_interaction(
        agent_id=STATIC_CONFIG.agent_id,
        input_message=body.message,
        output_message=result.content,
        tools_used=result.tools_used,
        user_id=auth_user.userid,
        user_name=auth_user.username,
    )

    return InfraSearchInvokeResponse(
        agent_id=STATIC_CONFIG.agent_id,
        content=result.content,
        tools_used=[
            {"name": tool.name, "mcp_server": tool.mcp_server} for tool in result.tools_used
        ],
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
