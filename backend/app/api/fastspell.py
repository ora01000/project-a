"""Authenticated proxy for fastspell (한글 초성/제시어) search."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, Request

from backend.app.config import resolve_fastspell_base_url
from backend.app.middleware.session_auth import get_request_auth_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["fastspell"])

_SEARCH_TIMEOUT = httpx.Timeout(connect=2.0, read=2.0, write=2.0, pool=2.0)


@router.get("/fastspell/search")
async def fastspell_search(
    request: Request,
    q: str = Query(default="", max_length=64),
    l: str = Query(default="", max_length=64, description="fastspell index label"),
    n: int = Query(default=10, ge=1, le=50),
) -> dict[str, Any]:
    """Proxy ``GET /search?q=&l=&n=`` to fastspell. Response: ``{"q": "...", "r": [...]}``."""
    get_request_auth_user(request)
    query = (q or "").strip()
    label = (l or "").strip()
    if not query:
        return {"q": "", "r": []}
    if not label:
        raise HTTPException(status_code=400, detail="label required")

    base = resolve_fastspell_base_url()
    url = f"{base}/search"
    params = {"q": query, "l": label, "n": n}
    try:
        async with httpx.AsyncClient(timeout=_SEARCH_TIMEOUT) as client:
            response = await client.get(url, params=params)
    except httpx.TimeoutException as exc:
        logger.warning("fastspell search timeout base=%s q=%r l=%r", base, query, label)
        raise HTTPException(status_code=504, detail="fastspell timeout") from exc
    except httpx.RequestError as exc:
        logger.warning("fastspell search error base=%s q=%r l=%r err=%s", base, query, label, exc)
        raise HTTPException(status_code=502, detail="fastspell unreachable") from exc

    if response.status_code == 400:
        raise HTTPException(status_code=400, detail=f"fastspell bad label: {label}")

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"fastspell status={response.status_code}",
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="fastspell invalid json") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="fastspell invalid body")

    results = payload.get("r")
    if not isinstance(results, list):
        results = []
    return {
        "q": str(payload.get("q", query)),
        "r": [str(item) for item in results if item is not None],
        "l": label,
    }
