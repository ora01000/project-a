"""Job request intake: validate inbound JSON and persist to jobs table."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.db.jobs import JobIntakePayload, JobRecord, create_job_from_intake

_REQUIRED_FIELDS = (
    "job_title",
    "requester_name",
    "requester_email",
    "requester_depart",
    "job_content",
    "request_date",
    "madang_id",
    "team_id",
    "channel_id",
    "message_id",
)


def _require_non_empty_string(payload: dict[str, Any], field: str) -> str:
    raw = payload.get(field)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{field} is required")
    return raw.strip()


def parse_job_intake_payload(payload: dict[str, Any]) -> JobIntakePayload:
    if not isinstance(payload, dict):
        raise ValueError("JSON payload must be an object")

    values = {field: _require_non_empty_string(payload, field) for field in _REQUIRED_FIELDS}
    return JobIntakePayload(**values)


def receive_job_request(database_path: str | Path, payload: dict[str, Any]) -> JobRecord:
    parsed = parse_job_intake_payload(payload)
    return create_job_from_intake(database_path, parsed)
