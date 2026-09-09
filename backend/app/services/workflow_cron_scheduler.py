"""Poll cron-enabled workflows and run them when due (infra_cluster-style)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.app.db.users import get_user_by_idx
from backend.app.db.workflow import disable_workflow_cron, list_scheduled_workflows
from backend.app.services.k8s_scrape_scheduler import cron_matches_minute
from backend.app.services.workflow_runner import run_workflow
from backend.app.timezone import DISPLAY_TIMEZONE, now_display_datetime

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = 30
DEFAULT_INITIAL_DELAY_SECONDS = 5


def _is_run_in_progress(last_start_date: str, last_end_date: str) -> bool:
    start = (last_start_date or "").strip()
    end = (last_end_date or "").strip()
    return bool(start) and not end


def is_one_shot_cron_expr(cron_expr: str) -> bool:
    """True when expr pins a calendar day+month (당일 1회 UI encodes this way)."""
    parts = (cron_expr or "").strip().split()
    if len(parts) != 5:
        return False
    day, month = parts[2], parts[3]
    return day.isdigit() and month.isdigit()


async def run_due_workflows(
    database_path: Path,
    agent_runtime: Any,
    *,
    fired_minutes: dict[str, str] | None = None,
    now: datetime | None = None,
) -> list[str]:
    """Run each cron-enabled workflow whose expression matches the current minute."""
    stamp_now = now or now_display_datetime()
    minute_key = stamp_now.astimezone(DISPLAY_TIMEZONE).strftime("%Y%m%d%H%M")
    tracking = fired_minutes if fired_minutes is not None else {}
    started: list[str] = []

    for record in list_scheduled_workflows(database_path):
        if not record.cron:
            continue
        expr = (record.cron_expr or "").strip()
        if not expr:
            continue
        if tracking.get(record.uuid) == minute_key:
            continue
        if not cron_matches_minute(expr, stamp_now):
            continue
        if _is_run_in_progress(record.last_start_date, record.last_end_date):
            logger.info(
                "workflow schedule skip in-progress uuid=%s name=%s",
                record.uuid,
                record.workflow_name,
            )
            tracking[record.uuid] = minute_key
            continue

        owner = get_user_by_idx(database_path, int(record.owner or 0))
        if owner is None:
            logger.warning(
                "workflow schedule skip missing owner uuid=%s owner=%s",
                record.uuid,
                record.owner,
            )
            tracking[record.uuid] = minute_key
            continue

        tracking[record.uuid] = minute_key
        logger.info(
            "workflow schedule due uuid=%s name=%s cron_expr=%s owner=%s",
            record.uuid,
            record.workflow_name,
            expr,
            owner.userid,
        )
        one_shot = is_one_shot_cron_expr(expr)
        try:
            await run_workflow(
                database_path=database_path,
                agent_runtime=agent_runtime,
                workflow_uuid=record.uuid,
                requester=owner,
            )
            started.append(record.uuid)
        except Exception:
            logger.exception(
                "workflow schedule failed uuid=%s name=%s",
                record.uuid,
                record.workflow_name,
            )
        finally:
            if one_shot:
                try:
                    disable_workflow_cron(database_path, record.uuid)
                    logger.info(
                        "workflow one-shot schedule disabled uuid=%s cron_expr=%s",
                        record.uuid,
                        expr,
                    )
                except Exception:
                    logger.exception(
                        "workflow one-shot schedule disable failed uuid=%s",
                        record.uuid,
                    )

    return started


async def run_workflow_cron_scheduler_loop(
    database_path: Path,
    agent_runtime: Any,
    *,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    initial_delay_seconds: int = DEFAULT_INITIAL_DELAY_SECONDS,
) -> None:
    if agent_runtime is None:
        logger.info("workflow cron scheduler skipped: agent_runtime unavailable")
        return

    interval = max(5, int(poll_interval_seconds))
    delay = max(0, int(initial_delay_seconds))
    if delay > 0:
        logger.info("workflow cron scheduler waiting %ss before first poll", delay)
        await asyncio.sleep(delay)

    logger.info("workflow cron scheduler started (poll_interval=%ss)", interval)
    fired_minutes: dict[str, str] = {}

    try:
        while True:
            try:
                due = await run_due_workflows(
                    database_path,
                    agent_runtime,
                    fired_minutes=fired_minutes,
                )
                if due:
                    logger.info("workflow cron scheduler started uuids=%s", due)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("workflow cron scheduler cycle failed: %s", exc)

            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("workflow cron scheduler stopped")
        raise
