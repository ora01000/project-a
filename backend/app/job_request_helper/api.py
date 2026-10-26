"""API for standalone JOB_REQUEST_HELPER."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.job_request_helper.agent import job_request_helper_service
from backend.app.job_request_helper.parse import parse_job_request_helper_content
from backend.app.job_request_helper.settings import STATIC_CONFIG
from backend.app.logging.agent_logger import log_agent_error, log_agent_interaction
from backend.app.middleware.session_auth import get_request_auth_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["job-request-helper"])


class JobRequestHelperInvokeRequest(BaseModel):
    message: str = Field(min_length=1)


class JobRequestHelperInvokeResponse(BaseModel):
    agent_id: str
    content: str
    title: str = ""
    form: str = ""
    tools_used: list[dict[str, str | None]]
    input_tokens: int = 0
    output_tokens: int = 0


@router.get("/job-request-helper/status")
async def job_request_helper_status(request: Request) -> dict:
    runtime_mode = str(getattr(request.app.state, "agent_runtime_mode", "mock")).strip().lower()
    status = job_request_helper_service.status()
    if runtime_mode == "http":
        status = {
            **status,
            "ready": request.app.state.agent_runtime is not None,
            "runtime_mode": "http",
            "execution": "external-axit",
            "local_agent_id": STATIC_CONFIG.agent_id,
            "tools": [],
        }
    return status


@router.post("/job-request-helper/invoke", response_model=JobRequestHelperInvokeResponse)
async def job_request_helper_invoke(
    body: JobRequestHelperInvokeRequest,
    request: Request,
) -> JobRequestHelperInvokeResponse:
    auth_user = get_request_auth_user(request)
    try:
        result = await job_request_helper_service.invoke(body.message)
    except Exception as exc:
        logger.exception("JOB_REQUEST_HELPER invoke failed")
        log_agent_error(
            STATIC_CONFIG.agent_id,
            reason=str(exc),
            input_message=body.message,
            user_id=auth_user.userid,
            user_name=auth_user.username,
        )
        raise HTTPException(
            status_code=500,
            detail=f"JOB_REQUEST_HELPER invoke failed: {exc}",
        ) from exc

    try:
        draft = parse_job_request_helper_content(result.content)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    log_agent_interaction(
        agent_id=STATIC_CONFIG.agent_id,
        input_message=body.message,
        output_message=result.content,
        tools_used=result.tools_used,
        user_id=auth_user.userid,
        user_name=auth_user.username,
    )

    return JobRequestHelperInvokeResponse(
        agent_id=STATIC_CONFIG.agent_id,
        content=result.content,
        title=draft.title,
        form=draft.form,
        tools_used=[
            {"name": tool.name, "mcp_server": tool.mcp_server} for tool in result.tools_used
        ],
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
