import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.app.config import load_whatap_settings
from backend.app.services.whatap_events import WhatapEventResult, handle_whatap_webhook

logger = logging.getLogger(__name__)

router = APIRouter(tags=["whatap"])


class WhatapWebhookResponse(BaseModel):
    status: str
    event_id: str
    received_at: str
    message: str


@router.post("/webhooks/whatap", response_model=WhatapWebhookResponse)
async def receive_whatap_webhook(request: Request) -> WhatapWebhookResponse:
    settings = load_whatap_settings()

    if settings.webhook_secret:
        provided_secret = request.headers.get("X-Whatap-Secret", "")
        if provided_secret != settings.webhook_secret:
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON payload must be an object")

    try:
        result: WhatapEventResult = await handle_whatap_webhook(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Whatap webhook processing failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to process Whatap event") from exc

    return WhatapWebhookResponse(
        status=result.status,
        event_id=result.event_id,
        received_at=result.received_at,
        message=result.message,
    )
