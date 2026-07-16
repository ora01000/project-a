from typing import Any

from fastapi import APIRouter, Query

from backend.app.logging.prompt_debug import clear_prompt_debug_entries, list_prompt_debug_entries

router = APIRouter(tags=["prompt-debug"])


@router.get("/prompt-debug")
async def get_prompt_debug(limit: int | None = Query(default=200, ge=1, le=1000)) -> list[dict[str, Any]]:
    return list_prompt_debug_entries(limit=limit)


@router.delete("/prompt-debug")
async def delete_prompt_debug() -> dict[str, int]:
    return {"deleted": clear_prompt_debug_entries()}
