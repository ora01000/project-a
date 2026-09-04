"""Background loop: pending received_mail → JOB_DECISION_AGENT (independent of IMAP/POP3)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from backend.app.config import JobDecisionLoopSettings, load_job_decision_loop_settings
from backend.app.services.job_decision_pipeline import process_pending_received_mails

logger = logging.getLogger(__name__)


async def run_job_decision_loop(
    database_path: Path,
    settings: JobDecisionLoopSettings | None = None,
) -> None:
    loop_settings = settings or load_job_decision_loop_settings()
    if not loop_settings.enabled:
        logger.info("job decision loop is disabled by config")
        return

    if loop_settings.initial_delay_seconds > 0:
        logger.info(
            "job decision loop waiting %ss before first cycle",
            loop_settings.initial_delay_seconds,
        )
        await asyncio.sleep(loop_settings.initial_delay_seconds)

    logger.info(
        "job decision loop started (poll_interval=%ss)",
        loop_settings.poll_interval_seconds,
    )

    try:
        while True:
            try:
                decided = await process_pending_received_mails(database_path)
                if decided:
                    logger.info("JOB_DECISION processed %s pending mail(s)", decided)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("job decision cycle failed: %s", exc)

            await asyncio.sleep(loop_settings.poll_interval_seconds)
    except asyncio.CancelledError:
        logger.info("job decision loop stopped")
        raise
