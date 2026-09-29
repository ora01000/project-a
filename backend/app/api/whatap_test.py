"""Admin-only Whatap webhook event test (simulates external Whatap delivery)."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.app.db.roles import is_admin_role
from backend.app.middleware.session_auth import get_request_auth_user
from backend.app.services.whatap_events import handle_whatap_webhook

router = APIRouter(tags=["whatap"])


class WhatapEventTestResponse(BaseModel):
    status: str
    event_id: str
    received_at: str
    message: str
    job_srnum: str | None = None


@router.post("/admin/whatap-event-test", response_model=WhatapEventTestResponse)
async def admin_whatap_event_test(
    request: Request,
    payload: dict[str, Any],
) -> WhatapEventTestResponse:
    viewer = get_request_auth_user(request)
    if not is_admin_role(viewer.role):
        raise HTTPException(status_code=403, detail="관리자만 수행할 수 있습니다.")

    if not payload:
        raise HTTPException(status_code=400, detail="JSON 객체를 입력해 주세요.")

    database_path = request.app.state.database_path
    try:
        result = await handle_whatap_webhook(payload, database_path=database_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Whatap 이벤트 처리에 실패했습니다.") from exc

    return WhatapEventTestResponse(
        status=result.status,
        event_id=result.event_id,
        received_at=result.received_at,
        message=result.message,
        job_srnum=result.job_srnum,
    )
