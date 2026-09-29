"""Periodically flush mynote content from Redis to durable storage."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from backend.app.config import MyNotesSettings, load_mynotes_settings
from backend.app.db.mynotes import (
    list_all_mynotes,
    persist_mynote_content,
    read_mynote_content,
)
from backend.app.services.mynote_content_store import (
    get_mynote_content_from_redis,
    hydrate_mynote_content,
)

logger = logging.getLogger(__name__)


async def flush_mynotes_to_storage(database_path: Path) -> int:
    settings = load_mynotes_settings()
    records = list_all_mynotes(database_path)
    flushed = 0

    for record in records:
        redis_content = await get_mynote_content_from_redis(record.userid, record.note_name)
        if redis_content is None:
            durable = read_mynote_content(record, database_path=database_path)
            await hydrate_mynote_content(record, file_content=durable)
            continue

        durable = read_mynote_content(record, database_path=database_path)
        if redis_content == durable:
            continue

        persist_mynote_content(database_path, record, redis_content)
        flushed += 1

    return flushed


async def flush_mynotes_to_filesystem(database_path: Path) -> int:
    """Backward-compatible alias."""
    return await flush_mynotes_to_storage(database_path)


async def run_mynote_flush_loop(
    database_path: Path,
    settings: MyNotesSettings | None = None,
) -> None:
    flush_settings = settings or load_mynotes_settings()
    if not flush_settings.enabled:
        logger.info("mynote flush loop is disabled")
        return

    if flush_settings.initial_delay_seconds > 0:
        logger.info(
            "mynote flush loop waiting %ss before first flush",
            flush_settings.initial_delay_seconds,
        )
        await asyncio.sleep(flush_settings.initial_delay_seconds)

    logger.info(
        "mynote flush loop started (flush_interval=%ss content_backend=%s)",
        flush_settings.flush_interval_seconds,
        flush_settings.content_backend,
    )

    try:
        while True:
            try:
                flushed = await flush_mynotes_to_storage(database_path)
                if flushed:
                    logger.info(
                        "mynote flush wrote %s note(s) to %s",
                        flushed,
                        flush_settings.content_backend,
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("mynote flush cycle failed: %s", exc)

            await asyncio.sleep(flush_settings.flush_interval_seconds)
    except asyncio.CancelledError:
        logger.info("mynote flush loop stopped")
        raise
