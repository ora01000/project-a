"""Periodically flush mynote content from Redis to the filesystem."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from backend.app.config import MyNotesSettings, load_mynotes_settings
from backend.app.db.mynotes import (
    list_all_mynotes,
    read_mynote_content,
    write_mynote_content_file,
)
from backend.app.services.mynote_content_store import (
    get_mynote_content_from_redis,
    hydrate_mynote_content,
)

logger = logging.getLogger(__name__)


async def flush_mynotes_to_filesystem(database_path: Path) -> int:
    records = list_all_mynotes(database_path)
    flushed = 0

    for record in records:
        redis_content = await get_mynote_content_from_redis(record.userid, record.note_name)
        if redis_content is None:
            file_content = read_mynote_content(record)
            await hydrate_mynote_content(record, file_content=file_content)
            continue

        file_content = read_mynote_content(record)
        if redis_content == file_content:
            continue

        write_mynote_content_file(record, redis_content)
        flushed += 1

    return flushed


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
        "mynote flush loop started (flush_interval=%ss)",
        flush_settings.flush_interval_seconds,
    )

    try:
        while True:
            try:
                flushed = await flush_mynotes_to_filesystem(database_path)
                if flushed:
                    logger.info("mynote flush wrote %s note(s) to filesystem", flushed)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("mynote flush cycle failed: %s", exc)

            await asyncio.sleep(flush_settings.flush_interval_seconds)
    except asyncio.CancelledError:
        logger.info("mynote flush loop stopped")
        raise
