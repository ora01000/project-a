"""Background loop: IMAP/POP3 poll → received_mail (worker / BACKEND_ROLE=all)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from backend.app.config import ReceivedMailSettings, load_received_mail_settings
from backend.app.services.mail_receive_poller import poll_received_mail_once

logger = logging.getLogger(__name__)


async def run_mail_receive_loop(
    database_path: Path,
    settings: ReceivedMailSettings | None = None,
) -> None:
    poll_settings = settings or load_received_mail_settings()
    if not poll_settings.poll_enabled:
        logger.info("mail receive loop is disabled by config")
        return

    if poll_settings.initial_delay_seconds > 0:
        logger.info(
            "mail receive loop waiting %ss before first poll",
            poll_settings.initial_delay_seconds,
        )
        await asyncio.sleep(poll_settings.initial_delay_seconds)

    logger.info(
        "mail receive loop started (poll_interval=%ss attachment_home=%s)",
        poll_settings.poll_interval_seconds,
        poll_settings.attachment_home,
    )

    try:
        while True:
            try:
                stored = await asyncio.to_thread(
                    poll_received_mail_once,
                    database_path,
                    poll_settings,
                )
                if stored:
                    logger.info("mail receive stored %s message(s)", stored)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("mail receive cycle failed: %s", exc)

            await asyncio.sleep(poll_settings.poll_interval_seconds)
    except asyncio.CancelledError:
        logger.info("mail receive loop stopped")
        raise
