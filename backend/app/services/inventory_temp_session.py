"""Track per-session temporary inventory tables for cleanup."""

from __future__ import annotations

import json
import logging

from backend.app.config import load_auth_session_settings
from backend.app.services.redis_client import get_redis

logger = logging.getLogger(__name__)

TEMP_KEY_PREFIX = "inventory:temp:"


def _temp_key(token: str) -> str:
    return f"{TEMP_KEY_PREFIX}{token}"


async def register_inventory_temp_table(token: str, tablename: str) -> None:
    name = (tablename or "").strip()
    if not token or not name:
        return
    settings = load_auth_session_settings()
    redis = get_redis()
    key = _temp_key(token)
    raw = await redis.get(key)
    tables: list[str] = []
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                tables = [str(item) for item in parsed if str(item).strip()]
        except (TypeError, ValueError, json.JSONDecodeError):
            tables = []
    if name not in tables:
        tables.append(name)
    await redis.setex(key, settings.ttl_seconds, json.dumps(tables))


async def unregister_inventory_temp_table(token: str, tablename: str) -> None:
    name = (tablename or "").strip()
    if not token or not name:
        return
    redis = get_redis()
    key = _temp_key(token)
    raw = await redis.get(key)
    if not raw:
        return
    try:
        parsed = json.loads(raw)
        tables = [str(item) for item in parsed if str(item).strip()] if isinstance(parsed, list) else []
    except (TypeError, ValueError, json.JSONDecodeError):
        tables = []
    next_tables = [item for item in tables if item != name]
    if not next_tables:
        await redis.delete(key)
        return
    settings = load_auth_session_settings()
    await redis.setex(key, settings.ttl_seconds, json.dumps(next_tables))


async def list_inventory_temp_tables(token: str) -> list[str]:
    if not token:
        return []
    redis = get_redis()
    raw = await redis.get(_temp_key(token))
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


async def clear_inventory_temp_tables(token: str) -> list[str]:
    """Return and clear registered temp tables for the session."""
    tables = await list_inventory_temp_tables(token)
    if token:
        await get_redis().delete(_temp_key(token))
    return tables
