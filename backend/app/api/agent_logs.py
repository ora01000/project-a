from typing import Any

from fastapi import APIRouter, Query

from backend.app.logging.agent_logger import list_all_agent_logs

router = APIRouter(tags=["agent-logs"])


@router.get("/agent-logs")
async def get_agent_logs(limit: int | None = Query(default=500, ge=1, le=5000)) -> list[dict[str, Any]]:
    return list_all_agent_logs(limit=limit)
