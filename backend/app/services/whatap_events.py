import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from backend.app.db.job_datetime import normalize_job_datetime, now_job_datetime
from backend.app.db.jobs import (
    build_whatap_event_job_title,
    create_whatap_event_job,
)
from backend.app.logging.agent_logger import log_agent_interaction
from backend.app.services.whatap_constants import WHATAP_EVENT_LOG_SOURCE
from backend.app.timezone import DISPLAY_TIMEZONE, format_display_datetime

logger = logging.getLogger(__name__)

WHATAP_JOB_CONTENT_PREFIX = (
    "The following JSON represents an event generated in WhaTap. "
    "Please identify the infrastructure involved (Kubernetes, KubeVirt, or VMware), "
    "analyze the event details, and examine the current status of the problematic resource "
    "using the appropriate agent"
)


class WhatapEventPayload(BaseModel):
    """Whatap webhook JSON payload. Fields are optional to accept varying event shapes."""

    event_type: str | None = Field(default=None, alias="eventType")
    project_name: str | None = Field(default=None, alias="projectName")
    server_name: str | None = Field(default=None, alias="serverName")
    metric_name: str | None = Field(default=None, alias="metricName")
    level: str | None = None
    message: str | None = None
    timestamp: str | None = None
    time: str | int | float | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True, "extra": "allow"}


class WhatapEventResult(BaseModel):
    status: str
    event_id: str
    received_at: str
    message: str
    job_srnum: str | None = None


def _generate_event_id() -> str:
    return datetime.now(UTC).strftime("whatap-%Y%m%d%H%M%S%f")


def _normalize_payload(payload: dict[str, Any]) -> WhatapEventPayload:
    return WhatapEventPayload.model_validate({**payload, "raw": payload})


def _parse_whatap_event_time(raw: dict[str, Any]) -> str:
    value = raw.get("time")
    if value is None:
        value = raw.get("timestamp")

    if value is None:
        return now_job_datetime()

    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 1e12:
            seconds /= 1000.0
        event_dt = datetime.fromtimestamp(seconds, tz=UTC).astimezone(DISPLAY_TIMEZONE)
        return format_display_datetime(event_dt)

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return now_job_datetime()
        try:
            return normalize_job_datetime(stripped)
        except ValueError:
            try:
                numeric = float(stripped)
            except ValueError:
                logger.warning("Unsupported Whatap event time value: %r", value)
                return now_job_datetime()
            if numeric > 1e12:
                numeric /= 1000.0
            event_dt = datetime.fromtimestamp(numeric, tz=UTC).astimezone(DISPLAY_TIMEZONE)
            return format_display_datetime(event_dt)

    logger.warning("Unsupported Whatap event time type: %r", value)
    return now_job_datetime()


def _build_whatap_job_content(payload: dict[str, Any]) -> str:
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
    return f"{WHATAP_JOB_CONTENT_PREFIX}\n{payload_json}"


def _create_job_from_whatap_event(
    database_path: str | Path,
    event: WhatapEventPayload,
    payload: dict[str, Any],
):
    job_title = build_whatap_event_job_title(event.project_name)
    job_content = _build_whatap_job_content(payload)
    request_date = _parse_whatap_event_time(payload)
    return create_whatap_event_job(
        database_path,
        job_title=job_title,
        job_content=job_content,
        request_date=request_date,
    )


async def handle_whatap_webhook(
    payload: dict[str, Any],
    *,
    database_path: str | Path,
) -> WhatapEventResult:
    if not payload:
        raise ValueError("Empty JSON payload")

    event = _normalize_payload(payload)
    event_id = _generate_event_id()
    received_at = datetime.now(UTC).isoformat()

    job = _create_job_from_whatap_event(database_path, event, payload)

    summary = (
        f"Whatap 이벤트 수신 및 작업 자동 제출: srnum={job.srnum}, "
        f"type={event.event_type or 'unknown'}, "
        f"project={event.project_name or 'unknown'}, "
        f"server={event.server_name or 'unknown'}, "
        f"level={event.level or 'unknown'}"
    )
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
    log_agent_interaction(
        agent_id=WHATAP_EVENT_LOG_SOURCE,
        input_message=payload_json,
        output_message=summary,
        tools_used=[],
    )

    return WhatapEventResult(
        status="received",
        event_id=event_id,
        received_at=received_at,
        message=summary,
        job_srnum=job.srnum,
    )
