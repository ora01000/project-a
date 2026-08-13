"""API for standalone JOB_DECISION_AGENT."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.job_decision_agent.agent import job_decision_agent_service
from backend.app.job_decision_agent.settings import STATIC_CONFIG
from backend.app.logging.agent_logger import log_agent_error, log_agent_interaction
from backend.app.middleware.session_auth import get_request_auth_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["job-decision-agent"])


class JobDecisionInvokeRequest(BaseModel):
    message: str = Field(min_length=1)


class JobDecisionInvokeResponse(BaseModel):
    agent_id: str
    content: str
    tools_used: list[dict[str, str | None]]
    input_tokens: int = 0
    output_tokens: int = 0


class JobDecisionEvaluateRequest(BaseModel):
    uuid: str = Field(min_length=1, max_length=36)
    persist: bool = True


class JobDecisionEvaluateResponse(BaseModel):
    agent_id: str
    uuid: str
    decision_type: int
    persisted: bool
    content: str
    tools_used: list[dict[str, str | None]]
    input_tokens: int = 0
    output_tokens: int = 0
    record: dict[str, Any] | None = None


@router.get("/job-decision-agent/status")
async def job_decision_agent_status() -> dict:
    return job_decision_agent_service.status()


@router.post("/job-decision-agent/invoke", response_model=JobDecisionInvokeResponse)
async def job_decision_agent_invoke(
    body: JobDecisionInvokeRequest,
    request: Request,
) -> JobDecisionInvokeResponse:
    auth_user = get_request_auth_user(request)
    try:
        result = await job_decision_agent_service.invoke(body.message)
    except Exception as exc:
        logger.exception("JOB_DECISION_AGENT invoke failed")
        log_agent_error(
            STATIC_CONFIG.agent_id,
            reason=str(exc),
            input_message=body.message,
            user_id=auth_user.userid,
            user_name=auth_user.username,
        )
        raise HTTPException(
            status_code=500,
            detail=f"JOB_DECISION_AGENT invoke failed: {exc}",
        ) from exc

    log_agent_interaction(
        agent_id=STATIC_CONFIG.agent_id,
        input_message=body.message,
        output_message=result.content,
        tools_used=result.tools_used,
        user_id=auth_user.userid,
        user_name=auth_user.username,
    )
    return JobDecisionInvokeResponse(
        agent_id=STATIC_CONFIG.agent_id,
        content=result.content,
        tools_used=[
            {"name": tool.name, "mcp_server": tool.mcp_server} for tool in result.tools_used
        ],
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )


@router.post("/job-decision-agent/evaluate", response_model=JobDecisionEvaluateResponse)
async def job_decision_agent_evaluate(
    body: JobDecisionEvaluateRequest,
    request: Request,
) -> JobDecisionEvaluateResponse:
    """Classify a received_mail uuid and optionally persist decision_type."""
    auth_user = get_request_auth_user(request)
    try:
        outcome = await job_decision_agent_service.evaluate_received_mail(
            request.app.state.database_path,
            body.uuid,
            persist=body.persist,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("JOB_DECISION_AGENT evaluate failed uuid=%s", body.uuid)
        log_agent_error(
            STATIC_CONFIG.agent_id,
            reason=str(exc),
            input_message=f"evaluate uuid={body.uuid}",
            user_id=auth_user.userid,
            user_name=auth_user.username,
        )
        raise HTTPException(
            status_code=500,
            detail=f"JOB_DECISION_AGENT evaluate failed: {exc}",
        ) from exc

    log_agent_interaction(
        agent_id=STATIC_CONFIG.agent_id,
        input_message=f"evaluate uuid={body.uuid}",
        output_message=str(outcome.get("content") or ""),
        tools_used=[],
        user_id=auth_user.userid,
        user_name=auth_user.username,
    )
    return JobDecisionEvaluateResponse(
        agent_id=STATIC_CONFIG.agent_id,
        uuid=str(outcome["uuid"]),
        decision_type=int(outcome["decision_type"]),
        persisted=bool(outcome["persisted"]),
        content=str(outcome["content"]),
        tools_used=list(outcome.get("tools_used") or []),
        input_tokens=int(outcome.get("input_tokens") or 0),
        output_tokens=int(outcome.get("output_tokens") or 0),
        record=outcome.get("record"),
    )
