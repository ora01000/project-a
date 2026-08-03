from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis.asyncio as redis

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


async def init_redis(url: str) -> redis.Redis:
    import redis.asyncio as redis_module

    global _client
    if _client is not None:
        return _client

    client = redis_module.from_url(url, decode_responses=True)
    await client.ping()
    _client = client
    logger.info("Redis connected: %s", url.split("@")[-1])
    return _client


async def close_redis() -> None:
    global _client
    if _client is None:
        return
    await _client.aclose()
    _client = None


def get_redis() -> redis.Redis:
    if _client is None:
        raise RuntimeError("Redis client is not initialized")
    return _client
