"""Admin Postman-style raw HTTP debugging endpoint."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.db.roles import is_admin_role
from backend.app.services.postman_debug import PostmanDebugError, execute_raw_http_request

router = APIRouter(tags=["debug"])


class PostmanDebugRequest(BaseModel):
    viewer_role: int
    call_info: str = Field(min_length=1)


class PostmanDebugResponse(BaseModel):
    status_code: int
    reason: str
    headers: dict[str, str]
    body: str
    elapsed_ms: float
    raw_response: str


def _require_admin(viewer_role: int) -> None:
    if not is_admin_role(viewer_role):
        raise HTTPException(status_code=403, detail="관리자만 수행할 수 있습니다.")


@router.post("/debug/postman", response_model=PostmanDebugResponse)
async def send_postman_debug_request(payload: PostmanDebugRequest) -> dict[str, Any]:
    _require_admin(payload.viewer_role)
    try:
        return await execute_raw_http_request(payload.call_info)
    except PostmanDebugError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
