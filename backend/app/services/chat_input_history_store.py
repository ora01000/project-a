"""Redis-backed per-user chat input history for the integrated terminal."""

from __future__ import annotations

import json
import logging
import urllib.parse

from backend.app.db.mynotes import _sanitize_user_id
from backend.app.services.redis_client import get_redis

logger = logging.getLogger(__name__)

CHAT_INPUT_HISTORY_PREFIX = "chat:input-history:"
MAX_CHAT_INPUT_HISTORY = 10


def _sanitize_agent_id(agent_id: str) -> str:
    normalized = agent_id.strip()
    if not normalized:
        raise ValueError("agent_id is required")
    return urllib.parse.quote(normalized, safe="")


def build_chat_input_history_key(userid: str, agent_id: str) -> str:
    safe_userid = _sanitize_user_id(userid)
    safe_agent_id = _sanitize_agent_id(agent_id)
    return f"{CHAT_INPUT_HISTORY_PREFIX}{safe_userid}:{safe_agent_id}"


def _parse_history_payload(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Invalid chat input history JSON in Redis")
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


async def get_chat_input_history(userid: str, agent_id: str) -> list[str]:
    redis = get_redis()
    key = build_chat_input_history_key(userid, agent_id)
    raw = await redis.get(key)
    history = _parse_history_payload(raw)
    if len(history) > MAX_CHAT_INPUT_HISTORY:
        history = history[-MAX_CHAT_INPUT_HISTORY:]
    return history


async def append_chat_input_history(userid: str, agent_id: str, message: str) -> list[str]:
    trimmed = message.strip()
    if not trimmed:
        return await get_chat_input_history(userid, agent_id)

    history = await get_chat_input_history(userid, agent_id)
    history = [item for item in history if item != trimmed]
    history.append(trimmed)
    next_history = history[-MAX_CHAT_INPUT_HISTORY:]

    redis = get_redis()
    key = build_chat_input_history_key(userid, agent_id)
    await redis.set(key, json.dumps(next_history, ensure_ascii=False))
    return next_history
