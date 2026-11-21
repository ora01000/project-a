"""Job request intake: validate inbound JSON and persist to jobs table."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.db.jobs import JobIntakePayload, JobRecord, create_job_from_intake
from backend.app.db.users import get_user_by_idx, get_user_idx_by_userid

_REQUIRED_FIELDS = (
    "job_title",
    "requester_email",
    "requester_depart",
    "job_content",
    "request_date",
    "team_id",
    "channel_id",
    "message_id",
)

# Legacy string identifiers accepted from external callers (resolved to users.idx).
_LEGACY_USERID_FIELDS = ("userid", "madang_id")


def _require_non_empty_string(payload: dict[str, Any], field: str) -> str:
    raw = payload.get(field)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{field} is required")
    return raw.strip()


def _parse_requester_idx(raw: Any) -> int | None:
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    raise ValueError("requester_idx must be an integer")


def resolve_requester_idx(database_path: str | Path, payload: dict[str, Any]) -> int:
    """Resolve requester users.idx (prefer legacy userid string → idx, else requester_idx)."""
    for field in _LEGACY_USERID_FIELDS:
        raw = payload.get(field)
        if not isinstance(raw, str) or not raw.strip():
            continue
        resolved = get_user_idx_by_userid(database_path, raw)
        if resolved is None:
            raise ValueError(f"unknown requester userid: {raw.strip()}")
        return resolved

    requester_idx = _parse_requester_idx(payload.get("requester_idx"))
    if requester_idx is None:
        raise ValueError("requester_idx is required")
    if get_user_by_idx(database_path, requester_idx) is None:
        raise ValueError(f"unknown requester_idx: {requester_idx}")
    return requester_idx


def parse_job_intake_payload(
    payload: dict[str, Any],
    *,
    database_path: str | Path,
) -> JobIntakePayload:
    if not isinstance(payload, dict):
        raise ValueError("JSON payload must be an object")

    values = {field: _require_non_empty_string(payload, field) for field in _REQUIRED_FIELDS}
    requester_idx = resolve_requester_idx(database_path, payload)
    return JobIntakePayload(requester_idx=requester_idx, **values)


def receive_job_request(database_path: str | Path, payload: dict[str, Any]) -> JobRecord:
    parsed = parse_job_intake_payload(payload, database_path=database_path)
    return create_job_from_intake(database_path, parsed)
