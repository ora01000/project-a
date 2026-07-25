"""Internal APIs used by the remote Agent Runtime service."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from backend.app.agent_runtime.schemas import (
    RuntimeInventoryApprovalRequest,
    RuntimeInventoryApprovalResponse,
)
from backend.app.services.inventory_approval import request_runtime_inventory_approval

router = APIRouter(prefix="/internal/runtime", tags=["runtime-internal"])


@router.post(
    "/inventory-approvals/request",
    response_model=RuntimeInventoryApprovalResponse,
)
async def runtime_inventory_approval_request(
    payload: RuntimeInventoryApprovalRequest,
    request: Request,
) -> RuntimeInventoryApprovalResponse:
    expected_key = getattr(request.app.state, "runtime_api_key", "")
    if expected_key:
        provided = request.headers.get("X-Runtime-Api-Key", "")
        if provided != expected_key:
            raise HTTPException(status_code=401, detail="Invalid runtime API key")

    approved = await request_runtime_inventory_approval(
        trace_id=payload.trace_id,
        caller_agent_id=payload.caller_agent_id,
        caller_agent_name=payload.caller_agent_name,
        query=payload.query,
    )
    return RuntimeInventoryApprovalResponse(approved=approved)
