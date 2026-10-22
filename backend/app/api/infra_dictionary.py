"""Authenticated API for job-intake infra dictionary helper."""

from __future__ import annotations

from fastapi import APIRouter, Request

from backend.app.middleware.session_auth import get_request_auth_user
from backend.app.services.infra_dictionary import read_infra_dictionary

router = APIRouter(tags=["infra-dictionary"])


@router.get("/infra-dictionary")
async def get_infra_dictionary(request: Request) -> dict:
    get_request_auth_user(request)
    return await read_infra_dictionary()
