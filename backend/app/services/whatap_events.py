import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from backend.app.agents.system_agents import WHATAP_EVENT_AGENT
from backend.app.logging.agent_logger import log_agent_interaction

logger = logging.getLogger(__name__)


class WhatapEventPayload(BaseModel):
    """Whatap webhook JSON payload. Fields are optional to accept varying event shapes."""

    event_type: str | None = Field(default=None, alias="eventType")
    project_name: str | None = Field(default=None, alias="projectName")
    server_name: str | None = Field(default=None, alias="serverName")
    metric_name: str | None = Field(default=None, alias="metricName")
    level: str | None = None
    message: str | None = None
    timestamp: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True, "extra": "allow"}


class WhatapEventResult(BaseModel):
    status: str
    event_id: str
    received_at: str
    message: str


def _generate_event_id() -> str:
    return datetime.now(UTC).strftime("whatap-%Y%m%d%H%M%S%f")


def _normalize_payload(payload: dict[str, Any]) -> WhatapEventPayload:
    return WhatapEventPayload.model_validate({**payload, "raw": payload})


async def _process_event(event: WhatapEventPayload) -> None:
    """Placeholder for downstream Whatap event processing.

    Future implementations may:
    - persist events to database
    - trigger job workflows
    - send notifications (email/Teams)
    - correlate with inventory data
    """
    logger.info(
        "Whatap event received (stub): type=%s project=%s server=%s level=%s",
        event.event_type,
        event.project_name,
        event.server_name,
        event.level,
    )


async def handle_whatap_webhook(payload: dict[str, Any]) -> WhatapEventResult:
    if not payload:
        raise ValueError("Empty JSON payload")

    event = _normalize_payload(payload)
    event_id = _generate_event_id()
    received_at = datetime.now(UTC).isoformat()

    await _process_event(event)

    summary = (
        f"Whatap 이벤트 수신: type={event.event_type or 'unknown'}, "
        f"project={event.project_name or 'unknown'}, "
        f"server={event.server_name or 'unknown'}, "
        f"level={event.level or 'unknown'}"
    )
    log_agent_interaction(
        agent_id=WHATAP_EVENT_AGENT.agent_id,
        input_message=str(payload),
        output_message=summary,
        tools_used=[],
    )

    return WhatapEventResult(
        status="received",
        event_id=event_id,
        received_at=received_at,
        message=summary,
    )
