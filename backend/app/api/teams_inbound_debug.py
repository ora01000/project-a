"""Debug endpoints for inbound Teams / Power Automate webhook payloads."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.app.services.teams_inbound_debug import (
    dismiss_teams_inbound_message,
    list_pending_teams_inbound_messages,
    record_teams_inbound_message,
)

router = APIRouter(tags=["debug"])


class TeamsInboundDebugEntryResponse(BaseModel):
    id: int
    received_at: str
    content_type: str
    headers: dict[str, str]
    body_text: str
    dismissed: bool


class TeamsInboundReceiveResponse(BaseModel):
    ok: bool
    id: int
    received_at: str


class TeamsInboundPendingResponse(BaseModel):
    messages: list[TeamsInboundDebugEntryResponse]


class DismissResponse(BaseModel):
    ok: bool


_SKIP_HEADERS = {"host", "content-length", "connection", "accept-encoding"}


def _capture_headers(request: Request) -> dict[str, str]:
    return {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in _SKIP_HEADERS
    }


@router.post(
    "/debug/teams-power-automate",
    response_model=TeamsInboundReceiveResponse,
    status_code=201,
)
async def receive_teams_power_automate_message(request: Request) -> TeamsInboundReceiveResponse:
    raw_body = await request.body()
    content_type = request.headers.get("content-type", "")
    entry = record_teams_inbound_message(
        raw_body=raw_body,
        content_type=content_type,
        headers=_capture_headers(request),
    )
    return TeamsInboundReceiveResponse(
        ok=True,
        id=entry.id,
        received_at=entry.received_at,
    )


@router.get("/debug/teams-power-automate/pending", response_model=TeamsInboundPendingResponse)
async def get_pending_teams_power_automate_messages() -> TeamsInboundPendingResponse:
    messages = [
        TeamsInboundDebugEntryResponse(**entry.to_dict())
        for entry in list_pending_teams_inbound_messages()
    ]
    return TeamsInboundPendingResponse(messages=messages)


@router.post("/debug/teams-power-automate/{entry_id}/dismiss", response_model=DismissResponse)
async def dismiss_teams_power_automate_message(entry_id: int) -> dict[str, Any]:
    if not dismiss_teams_inbound_message(entry_id):
        raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다.")
    return {"ok": True}
