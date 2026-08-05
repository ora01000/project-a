from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from backend.app.db.roles import is_admin_role
from backend.app.logging.agent_logger import list_all_agent_logs
from backend.app.middleware.session_auth import get_request_auth_user
from backend.app.services.whatap_constants import (
    WHATAP_EVENT_LOG_SOURCE,
    expand_whatap_log_filter_ids,
)

router = APIRouter(tags=["agent-logs"])


def _parse_exclude_agent_ids(raw: str | None) -> frozenset[str]:
    if not raw:
        return frozenset()
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


@router.get("/agent-logs")
async def get_agent_logs(
    request: Request,
    limit: int | None = Query(default=500, ge=1, le=5000),
    agent_id: str | None = Query(default=None),
    exclude_agent_id: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    viewer = get_request_auth_user(request)
    admin_view = is_admin_role(viewer.role)
    normalized_agent_id = (agent_id or "").strip() or None
    exclude_agent_ids = expand_whatap_log_filter_ids(_parse_exclude_agent_ids(exclude_agent_id))

    if normalized_agent_id == WHATAP_EVENT_LOG_SOURCE and WHATAP_EVENT_LOG_SOURCE in exclude_agent_ids:
        raise HTTPException(status_code=400, detail="Whatap 이벤트 로그는 exclude_agent_id로 제외할 수 없습니다.")

    return list_all_agent_logs(
        limit=limit,
        viewer_user_id=viewer.userid,
        admin_view=admin_view,
        agent_id=normalized_agent_id,
        exclude_agent_ids=exclude_agent_ids or None,
    )
