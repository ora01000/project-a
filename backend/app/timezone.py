"""Display timezone helpers (fixed to Asia/Seoul)."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DISPLAY_TIMEZONE_NAME = "Asia/Seoul"
DISPLAY_TIMEZONE = ZoneInfo(DISPLAY_TIMEZONE_NAME)
JOB_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def now_display_datetime() -> datetime:
    return datetime.now(DISPLAY_TIMEZONE)


def format_display_datetime(
    dt: datetime | None = None,
    *,
    fmt: str = JOB_DATETIME_FORMAT,
) -> str:
    current = dt if dt is not None else now_display_datetime()
    if current.tzinfo is None:
        current = current.replace(tzinfo=DISPLAY_TIMEZONE)
    else:
        current = current.astimezone(DISPLAY_TIMEZONE)
    return current.strftime(fmt)


def display_datetime_after(delta: timedelta, *, base: datetime | None = None) -> str:
    start = base if base is not None else now_display_datetime()
    if start.tzinfo is None:
        start = start.replace(tzinfo=DISPLAY_TIMEZONE)
    else:
        start = start.astimezone(DISPLAY_TIMEZONE)
    return format_display_datetime(start + delta)
