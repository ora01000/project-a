"""Teams / Power Automate inbound debug messages — Redis-backed for multi-pod share."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from backend.app.services.redis_client import get_redis
from backend.app.timezone import format_display_datetime, now_display_datetime

logger = logging.getLogger(__name__)

_MAX_ENTRIES = 200
_SEQ_KEY = "teams_inbound_debug:seq"
_IDS_KEY = "teams_inbound_debug:ids"
_PENDING_KEY = "teams_inbound_debug:pending"
_ENTRY_KEY_PREFIX = "teams_inbound_debug:entry:"
# Keep debug payloads for a day even if not dismissed.
_ENTRY_TTL_SECONDS = 86_400


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

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> TeamsInboundDebugEntry:
        parsed = json.loads(raw)
        headers_raw = parsed.get("headers") or {}
        headers = {str(k): str(v) for k, v in headers_raw.items()} if isinstance(headers_raw, dict) else {}
        return cls(
            id=int(parsed["id"]),
            received_at=str(parsed.get("received_at") or ""),
            content_type=str(parsed.get("content_type") or "application/octet-stream"),
            headers=headers,
            body_text=str(parsed.get("body_text") or ""),
            dismissed=bool(parsed.get("dismissed")),
        )


def _entry_key(entry_id: int) -> str:
    return f"{_ENTRY_KEY_PREFIX}{int(entry_id)}"


def _format_body_for_display(raw_body: bytes, content_type: str) -> str:
    text = raw_body.decode("utf-8", errors="replace")
    if "json" in content_type.lower() and text.strip():
        try:
            parsed = json.loads(text)
            return json.dumps(parsed, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            return text
    return text


async def record_teams_inbound_message(
    *,
    raw_body: bytes,
    content_type: str,
    headers: dict[str, str],
) -> TeamsInboundDebugEntry:
    body_text = _format_body_for_display(raw_body, content_type)
    received_at = format_display_datetime(now_display_datetime())
    redis = get_redis()

    entry_id = int(await redis.incr(_SEQ_KEY))
    entry = TeamsInboundDebugEntry(
        id=entry_id,
        received_at=received_at,
        content_type=content_type or "application/octet-stream",
        headers=headers,
        body_text=body_text,
    )

    pipe = redis.pipeline()
    pipe.setex(_entry_key(entry_id), _ENTRY_TTL_SECONDS, entry.to_json())
    pipe.lpush(_IDS_KEY, str(entry_id))
    pipe.ltrim(_IDS_KEY, 0, _MAX_ENTRIES - 1)
    pipe.sadd(_PENDING_KEY, str(entry_id))
    results = await pipe.execute()

    # Drop entries that fell off the retention window.
    kept_ids = await redis.lrange(_IDS_KEY, 0, -1)
    kept = set(kept_ids or [])
    pending_ids = await redis.smembers(_PENDING_KEY)
    stale = [pid for pid in (pending_ids or set()) if pid not in kept]
    if stale:
        cleanup = redis.pipeline()
        for pid in stale:
            cleanup.srem(_PENDING_KEY, pid)
            cleanup.delete(_entry_key(int(pid)))
        await cleanup.execute()

    del results  # pipeline executed; silence unused

    logger.info(
        "Teams/Power Automate inbound debug message #%s (%s bytes)\n%s",
        entry.id,
        len(raw_body),
        body_text,
    )
    return entry


async def list_pending_teams_inbound_messages() -> list[TeamsInboundDebugEntry]:
    redis = get_redis()
    pending_ids = await redis.smembers(_PENDING_KEY)
    if not pending_ids:
        return []

    # Preserve newest-first order using the ids list when possible.
    ordered_ids = await redis.lrange(_IDS_KEY, 0, -1)
    pending_set = set(pending_ids)
    id_order = [int(i) for i in (ordered_ids or []) if i in pending_set]
    # Include any pending ids missing from the list (should be rare).
    for raw_id in pending_ids:
        value = int(raw_id)
        if value not in id_order:
            id_order.append(value)

    if not id_order:
        return []

    keys = [_entry_key(i) for i in id_order]
    raw_entries = await redis.mget(keys)
    entries: list[TeamsInboundDebugEntry] = []
    missing: list[str] = []
    for entry_id, raw in zip(id_order, raw_entries, strict=False):
        if not raw:
            missing.append(str(entry_id))
            continue
        try:
            entry = TeamsInboundDebugEntry.from_json(raw)
        except (TypeError, ValueError, json.JSONDecodeError, KeyError):
            missing.append(str(entry_id))
            continue
        if entry.dismissed:
            missing.append(str(entry_id))
            continue
        entries.append(entry)

    if missing:
        pipe = redis.pipeline()
        for pid in missing:
            pipe.srem(_PENDING_KEY, pid)
        await pipe.execute()

    return entries


async def dismiss_teams_inbound_message(entry_id: int) -> bool:
    redis = get_redis()
    key = _entry_key(entry_id)
    raw = await redis.get(key)
    if not raw:
        await redis.srem(_PENDING_KEY, str(entry_id))
        return False
    try:
        entry = TeamsInboundDebugEntry.from_json(raw)
    except (TypeError, ValueError, json.JSONDecodeError, KeyError):
        await redis.srem(_PENDING_KEY, str(entry_id))
        return False

    entry.dismissed = True
    ttl = await redis.ttl(key)
    pipe = redis.pipeline()
    if ttl and ttl > 0:
        pipe.setex(key, ttl, entry.to_json())
    else:
        pipe.setex(key, _ENTRY_TTL_SECONDS, entry.to_json())
    pipe.srem(_PENDING_KEY, str(entry_id))
    await pipe.execute()
    return True
