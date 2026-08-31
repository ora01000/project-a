"""Thin API for the standalone INFRA_GAP_ANALYSIS agent."""

from __future__ import annotations

import logging

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.db.roles import can_run_gap_analysis
from backend.app.infra_gap_analysis.agent import infra_gap_analysis_service
from backend.app.infra_gap_analysis.generation_context import build_gap_analysis_user_message
from backend.app.infra_gap_analysis.settings import STATIC_CONFIG
from backend.app.logging.agent_logger import log_agent_error, log_agent_interaction
from backend.app.middleware.session_auth import get_request_auth_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["infra-gap-analysis"])


class InfraGapAnalysisInvokeRequest(BaseModel):
    cluster_name: str | None = Field(default=None, max_length=200)
    infra_type: str | None = Field(default=None, max_length=50)
    message: str | None = Field(default=None, min_length=1)

    def resolved_message(self, database_path: str | Path | None) -> str:
        if self.message and self.message.strip():
            return self.message.strip()
        cluster_name = (self.cluster_name or "").strip()
        infra_type = (self.infra_type or "").strip()
        if cluster_name and infra_type:
            return build_gap_analysis_user_message(
                cluster_name=cluster_name,
                infra_type=infra_type,
                database_path=database_path,
            )
        raise ValueError("cluster_name and infra_type are required when message is omitted")


class InfraGapAnalysisInvokeResponse(BaseModel):
    agent_id: str
    content: str
    tools_used: list[dict[str, str | None]]
    input_tokens: int = 0
    output_tokens: int = 0


def _require_gap_analysis_access(request: Request) -> None:
    viewer = get_request_auth_user(request)
    if not can_run_gap_analysis(viewer.role):
        raise HTTPException(status_code=403, detail="AI 갭분석 권한이 없습니다.")


@router.get("/infra-gap-analysis/status")
async def infra_gap_analysis_status() -> dict:
    return infra_gap_analysis_service.status()


@router.post("/infra-gap-analysis/invoke", response_model=InfraGapAnalysisInvokeResponse)
async def infra_gap_analysis_invoke(
    body: InfraGapAnalysisInvokeRequest,
    request: Request,
) -> InfraGapAnalysisInvokeResponse:
    _require_gap_analysis_access(request)
    auth_user = get_request_auth_user(request)
    database_path = getattr(request.app.state, "database_path", None)
    try:
        message = body.resolved_message(database_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        result = await infra_gap_analysis_service.invoke(message)
    except Exception as exc:
        logger.exception("INFRA_GAP_ANALYSIS invoke failed")
        log_agent_error(
            STATIC_CONFIG.agent_id,
            reason=str(exc),
            input_message=message,
            user_id=auth_user.userid,
            user_name=auth_user.username,
        )
        raise HTTPException(status_code=500, detail=f"INFRA_GAP_ANALYSIS invoke failed: {exc}") from exc

    log_agent_interaction(
        agent_id=STATIC_CONFIG.agent_id,
        input_message=message,
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
