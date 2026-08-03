from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass

from backend.app.services.redis_client import get_redis

SESSION_KEY_PREFIX = "auth:session:"


@dataclass(frozen=True)
class SessionData:
    user_idx: int
    userid: str
    created_at: float


def _session_key(token: str) -> str:
    return f"{SESSION_KEY_PREFIX}{token}"


def _encode_session(data: SessionData) -> str:
    return json.dumps(
        {
            "user_idx": data.user_idx,
            "userid": data.userid,
            "created_at": data.created_at,
        }
    )


def _decode_session(raw: str) -> SessionData:
    parsed = json.loads(raw)
    return SessionData(
        user_idx=int(parsed["user_idx"]),
        userid=str(parsed["userid"]),
        created_at=float(parsed["created_at"]),
    )


async def create_session(
    user_idx: int,
    userid: str,
    *,
    ttl_seconds: int,
) -> tuple[str, int]:
    token = secrets.token_urlsafe(32)
    now = time.time()
    data = SessionData(user_idx=user_idx, userid=userid, created_at=now)
    redis = get_redis()
    await redis.setex(_session_key(token), ttl_seconds, _encode_session(data))
    return token, ttl_seconds


async def validate_and_touch_session(
    token: str,
    *,
    ttl_seconds: int,
    absolute_max_seconds: int,
) -> SessionData | None:
    redis = get_redis()
    key = _session_key(token)
    raw = await redis.get(key)
    if not raw:
        return None

    data = _decode_session(raw)
    now = time.time()
    if now - data.created_at > absolute_max_seconds:
        await redis.delete(key)
        return None

    await redis.setex(key, ttl_seconds, raw)
    return data


async def revoke_session(token: str) -> None:
    redis = get_redis()
    await redis.delete(_session_key(token))
