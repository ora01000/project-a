"""In-memory store for Teams / Power Automate inbound debug messages."""

from __future__ import annotations

import json
import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from backend.app.timezone import format_display_datetime, now_display_datetime

logger = logging.getLogger(__name__)

_MAX_ENTRIES = 200


@dataclass
class TeamsInboundDebugEntry:
    id: int
    received_at: str
    content_type: str
    headers: dict[str, str]
    body_text: str
    dismissed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "received_at": self.received_at,
            "content_type": self.content_type,
            "headers": self.headers,
            "body_text": self.body_text,
            "dismissed": self.dismissed,
        }


@dataclass
class _Store:
    lock: threading.Lock = field(default_factory=threading.Lock)
    next_id: int = 1
    entries: deque[TeamsInboundDebugEntry] = field(default_factory=deque)


_store = _Store()


def _format_body_for_display(raw_body: bytes, content_type: str) -> str:
    text = raw_body.decode("utf-8", errors="replace")
    if "json" in content_type.lower() and text.strip():
        try:
            parsed = json.loads(text)
            return json.dumps(parsed, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            return text
    return text


def record_teams_inbound_message(
    *,
    raw_body: bytes,
    content_type: str,
    headers: dict[str, str],
) -> TeamsInboundDebugEntry:
    body_text = _format_body_for_display(raw_body, content_type)
    received_at = format_display_datetime(now_display_datetime())

    with _store.lock:
        entry = TeamsInboundDebugEntry(
            id=_store.next_id,
            received_at=received_at,
            content_type=content_type or "application/octet-stream",
            headers=headers,
            body_text=body_text,
        )
        _store.next_id += 1
        _store.entries.append(entry)
        while len(_store.entries) > _MAX_ENTRIES:
            _store.entries.popleft()

    logger.info(
        "Teams/Power Automate inbound debug message #%s (%s bytes)\n%s",
        entry.id,
        len(raw_body),
        body_text,
    )
    return entry


def list_pending_teams_inbound_messages() -> list[TeamsInboundDebugEntry]:
    with _store.lock:
        return [entry for entry in _store.entries if not entry.dismissed]


def dismiss_teams_inbound_message(entry_id: int) -> bool:
    with _store.lock:
        for entry in _store.entries:
            if entry.id == entry_id:
                entry.dismissed = True
                return True
    return False
