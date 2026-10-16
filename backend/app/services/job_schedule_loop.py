"""Release due scheduled jobs from jobs_scheduled so the job processor can run them."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from backend.app.config import JobProcessorSettings, load_job_processor_settings
from backend.app.db.jobs_scheduled import release_due_scheduled_jobs

logger = logging.getLogger(__name__)


async def run_job_schedule_loop(
    database_path: Path,
    *,
    settings: JobProcessorSettings | None = None,
) -> None:
    processor = settings or load_job_processor_settings()
    if not processor.enabled:
        logger.info("job schedule loop is disabled (job processor disabled)")
        return

    if processor.initial_delay_seconds > 0:
        await asyncio.sleep(processor.initial_delay_seconds)

    logger.info(
        "job schedule loop started (poll_interval=%ss)",
        processor.poll_interval_seconds,
    )
    try:
        while True:
            try:
                released = await asyncio.to_thread(release_due_scheduled_jobs, database_path)
                if released:
                    logger.info(
                        "job schedule released %s due job(s): %s",
                        len(released),
                        released,
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("job schedule poll cycle failed: %s", exc)
            await asyncio.sleep(processor.poll_interval_seconds)
    except asyncio.CancelledError:
        logger.info("job schedule loop stopped")
        raise
