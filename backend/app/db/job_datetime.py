"""Normalize job datetime strings to include seconds."""

from __future__ import annotations

import re
from datetime import datetime

from backend.app.timezone import JOB_DATETIME_FORMAT, format_display_datetime

_JOB_DATETIME_FORMAT = JOB_DATETIME_FORMAT
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def now_job_datetime() -> str:
    return format_display_datetime()


def request_date_yyyymmdd(request_date: str) -> str:
    """Extract YYYYMMDD from a job request_date value."""
    raw = (request_date or "").strip()
    if not raw:
        raise ValueError("request_date is empty")

    digits = re.sub(r"\D", "", raw)
    if len(digits) >= 8:
        return digits[:8]

    raise ValueError(f"cannot derive YYYYMMDD from request_date: {request_date!r}")


def build_sr_num(request_date: str, sequence: int) -> str:
    """SR + YYYYMMDD + _ + 5-digit daily sequence (00001..99999 per date)."""
    if sequence < 1 or sequence > 99_999:
        raise ValueError(f"srnum sequence out of range: {sequence}")
    return f"SR{request_date_yyyymmdd(request_date)}_{sequence:05d}"


def next_sr_sequence(connection, request_date: str) -> int:
    """Next 5-digit sequence for the request date; resets to 1 when YYYYMMDD changes."""
    yyyymmdd = request_date_yyyymmdd(request_date)
    prefix = f"SR{yyyymmdd}_"
    # PostgreSQL: SUBSTR(s, -5) does NOT mean "last 5 chars" (negative start → 1).
    row = connection.execute(
        """
        SELECT MAX(CAST(RIGHT(srnum, 5) AS INTEGER)) AS max_seq
        FROM jobs
        WHERE srnum LIKE ?
          AND LENGTH(srnum) >= 5
          AND RIGHT(srnum, 5) ~ '^[0-9]{5}$'
        """,
        (f"{prefix}%",),
    ).fetchone()
    if row is None:
        return 1
    raw = row["max_seq"] if hasattr(row, "keys") else row[0]
    current_max = int(raw) if raw is not None else 0
    return current_max + 1


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
