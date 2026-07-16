"""Normalize job datetime strings to include seconds."""

from __future__ import annotations

import re
from datetime import datetime

_JOB_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def now_job_datetime() -> str:
    return datetime.now().strftime(_JOB_DATETIME_FORMAT)


def normalize_job_datetime(value: str, *, default_time: str = "00:00:00") -> str:
    """Ensure datetime includes HH:MM:SS. Date-only values get default_time."""
    raw = (value or "").strip()
    if not raw:
        raise ValueError("datetime value is empty")

    if _DATE_ONLY.match(raw):
        return f"{raw} {default_time}"

    normalized = raw.replace("T", " ")
    # Drop timezone suffix if present.
    for separator in ("+", "Z"):
        if separator in normalized[10:]:
            idx = normalized.find(separator, 10)
            if idx != -1:
                normalized = normalized[:idx].rstrip()
                break

    if "." in normalized:
        normalized = normalized.split(".", 1)[0]

    parts = normalized.split(" ", 1)
    if len(parts) != 2:
        raise ValueError(f"unsupported datetime value: {value!r}")

    date_part, time_part = parts[0], parts[1]
    if not _DATE_ONLY.match(date_part):
        raise ValueError(f"unsupported datetime value: {value!r}")

    pieces = time_part.split(":")
    if len(pieces) == 2:
        hour, minute = pieces
        second = "00"
    elif len(pieces) >= 3:
        hour, minute, second = pieces[0], pieces[1], pieces[2][:2]
    else:
        raise ValueError(f"unsupported datetime value: {value!r}")

    try:
        parsed = datetime(
            int(date_part[0:4]),
            int(date_part[5:7]),
            int(date_part[8:10]),
            int(hour),
            int(minute),
            int(second),
        )
    except ValueError as exc:
        raise ValueError(f"unsupported datetime value: {value!r}") from exc

    return parsed.strftime(_JOB_DATETIME_FORMAT)
