"""Poll cron-enabled k8s clusters and run inventory scrape when due."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

from croniter import croniter

from backend.app.config import K8sCollectorSettings, load_k8s_collector_settings
from backend.app.db.k8s_inventory import INFRA_TYPE_VSPHERE, list_scheduled_k8s_clusters
from backend.app.services.k8s_collector import (
    KubeconfigRequiredError,
    collect_and_persist_cluster,
)
from backend.app.services.kubevirt_collector import collect_and_persist_kubevirt
from backend.app.services.vsphere_collector import (
    VsphereConnectTimeoutError,
    VsphereMockScrapeSkippedError,
    collect_and_persist_vsphere,
)
from backend.app.timezone import DISPLAY_TIMEZONE, now_display_datetime

logger = logging.getLogger(__name__)


def cron_matches_minute(cron_expr: str, when: datetime) -> bool:
    """True when ``when``'s minute is a scheduled fire time for cron_expr."""
    aware = when if when.tzinfo is not None else when.replace(tzinfo=DISPLAY_TIMEZONE)
    minute_start = aware.astimezone(DISPLAY_TIMEZONE).replace(second=0, microsecond=0)
    try:
        iterator = croniter(cron_expr, minute_start - timedelta(seconds=1))
        nxt = iterator.get_next(datetime)
    except (ValueError, KeyError, TypeError):
        return False
    if nxt.tzinfo is None:
        nxt = nxt.replace(tzinfo=DISPLAY_TIMEZONE)
    else:
        nxt = nxt.astimezone(DISPLAY_TIMEZONE)
    nxt = nxt.replace(second=0, microsecond=0)
    return nxt == minute_start


async def run_due_k8s_scrapes(
    database_path: Path,
    *,
    runtime_mode: str,
    settings: K8sCollectorSettings | None = None,
    fired_minutes: dict[int, str] | None = None,
    now: datetime | None = None,
) -> list[int]:
    """Collect each cron-enabled cluster whose expression matches the current minute.

    ``fired_minutes`` tracks ``cluster_idx -> YYYYMMDDHHMM`` so a due cluster is
    scraped at most once per minute even if the poll loop runs more often.
    """
    collector = settings or load_k8s_collector_settings()
    stamp_now = now or now_display_datetime()
    minute_key = stamp_now.astimezone(DISPLAY_TIMEZONE).strftime("%Y%m%d%H%M")
    tracking = fired_minutes if fired_minutes is not None else {}
    collected: list[int] = []

    for record in list_scheduled_k8s_clusters(database_path):
        if not record.cron:
            continue
        expr = (record.cron_expr or "").strip()
        if not expr:
            continue
        if tracking.get(record.idx) == minute_key:
            continue
        if not cron_matches_minute(expr, stamp_now):
            continue

        tracking[record.idx] = minute_key
        logger.info(
            "infra scrape schedule due cluster=%s idx=%s type=%s cron_expr=%s",
            record.cluster_name,
            record.idx,
            record.infra_type,
            expr,
        )
        try:
            if record.infra_type == "kubevirt":
                await asyncio.to_thread(
                    collect_and_persist_kubevirt,
                    database_path,
                    cluster_idx=record.idx,
                    cluster_name=record.cluster_name,
                    settings=collector,
                    runtime_mode=runtime_mode,
                )
            elif record.infra_type == INFRA_TYPE_VSPHERE:
                await asyncio.to_thread(
                    collect_and_persist_vsphere,
                    database_path,
                    cluster_idx=record.idx,
                    cluster_name=record.cluster_name,
                    runtime_mode=runtime_mode,
                )
            else:
                await asyncio.to_thread(
                    collect_and_persist_cluster,
                    database_path,
                    cluster_idx=record.idx,
                    cluster_name=record.cluster_name,
                    settings=collector,
                    runtime_mode=runtime_mode,
                )
            collected.append(record.idx)
        except KubeconfigRequiredError as exc:
            logger.warning(
                "infra scrape schedule skipped cluster=%s: %s",
                record.cluster_name,
                exc,
            )
        except (VsphereConnectTimeoutError, VsphereMockScrapeSkippedError) as exc:
            logger.warning(
                "infra scrape schedule skipped cluster=%s: %s",
                record.cluster_name,
                exc,
            )
        except Exception:
            logger.exception(
                "infra scrape schedule failed cluster=%s idx=%s",
                record.cluster_name,
                record.idx,
            )

    return collected


async def run_k8s_scrape_scheduler_loop(
    database_path: Path,
    *,
    runtime_mode: str,
    settings: K8sCollectorSettings | None = None,
) -> None:
    collector = settings or load_k8s_collector_settings()
    if not collector.schedule_enabled:
        logger.info("k8s scrape scheduler is disabled")
        return

    if collector.schedule_initial_delay_seconds > 0:
        logger.info(
            "k8s scrape scheduler waiting %ss before first poll",
            collector.schedule_initial_delay_seconds,
        )
        await asyncio.sleep(collector.schedule_initial_delay_seconds)

    logger.info(
        "k8s scrape scheduler started (poll_interval=%ss)",
        collector.schedule_poll_interval_seconds,
    )
    fired_minutes: dict[int, str] = {}

    try:
        while True:
            try:
                collected = await run_due_k8s_scrapes(
                    database_path,
                    runtime_mode=runtime_mode,
                    settings=collector,
                    fired_minutes=fired_minutes,
                )
                if collected:
                    logger.info(
                        "k8s scrape scheduler collected cluster idxs=%s",
                        collected,
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("k8s scrape scheduler cycle failed: %s", exc)

            await asyncio.sleep(collector.schedule_poll_interval_seconds)
    except asyncio.CancelledError:
        logger.info("k8s scrape scheduler stopped")
        raise
