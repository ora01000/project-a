"""Thin API for the standalone INFRA_GAP_ANALYSIS agent."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.infra_gap_analysis.agent import infra_gap_analysis_service
from backend.app.infra_gap_analysis.settings import STATIC_CONFIG
from backend.app.logging.agent_logger import log_agent_error, log_agent_interaction
from backend.app.middleware.session_auth import get_request_auth_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["infra-gap-analysis"])


class InfraGapAnalysisInvokeRequest(BaseModel):
    message: str = Field(min_length=1)
    cluster_name: str | None = Field(default=None, max_length=200)
    infra_type: str | None = Field(default=None, max_length=50)


class InfraGapAnalysisInvokeResponse(BaseModel):
    agent_id: str
    content: str
    tools_used: list[dict[str, str | None]]
    input_tokens: int = 0
    output_tokens: int = 0


@router.get("/infra-gap-analysis/status")
async def infra_gap_analysis_status() -> dict:
    return infra_gap_analysis_service.status()


@router.post("/infra-gap-analysis/invoke", response_model=InfraGapAnalysisInvokeResponse)
async def infra_gap_analysis_invoke(
    body: InfraGapAnalysisInvokeRequest,
    request: Request,
) -> InfraGapAnalysisInvokeResponse:
    auth_user = get_request_auth_user(request)
    try:
        result = await infra_gap_analysis_service.invoke(body.message)
    except Exception as exc:
        logger.exception("INFRA_GAP_ANALYSIS invoke failed")
        log_agent_error(
            STATIC_CONFIG.agent_id,
            reason=str(exc),
            input_message=body.message,
            user_id=auth_user.userid,
            user_name=auth_user.username,
        )
        raise HTTPException(status_code=500, detail=f"INFRA_GAP_ANALYSIS invoke failed: {exc}") from exc

    log_agent_interaction(
        agent_id=STATIC_CONFIG.agent_id,
        input_message=body.message,
        output_message=result.content,
        tools_used=result.tools_used,
        user_id=auth_user.userid,
        user_name=auth_user.username,
    )

    return InfraGapAnalysisInvokeResponse(
        agent_id=STATIC_CONFIG.agent_id,
        content=result.content,
        tools_used=[
            {"name": tool.name, "mcp_server": tool.mcp_server} for tool in result.tools_used
        ],
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
