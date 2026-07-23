"""Periodic sync collector for Kubernetes agent cluster inventories."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

from backend.app.agents.k8s_agent import K8S_CLUSTER_SPECS
from backend.app.config import K8sCollectorSettings, load_k8s_collector_settings
from backend.app.db.k8s_inventory import replace_cluster_snapshot
from backend.app.services.k8s_collector import collect_cluster_snapshot
from backend.app.timezone import DISPLAY_TIMEZONE, now_display_datetime

logger = logging.getLogger(__name__)


def scheduled_time_for_agent(
    agent_index: int,
    *,
    schedule_hour: int,
    schedule_minute: int,
    stagger_minutes: int,
    now: datetime | None = None,
) -> datetime:
    """Next local daily slot: base 00:10 + index * 5 minutes."""
    current = now or now_display_datetime()
    if current.tzinfo is None:
        local = current.replace(tzinfo=DISPLAY_TIMEZONE)
    else:
        local = current.astimezone(DISPLAY_TIMEZONE)
    base_minutes = schedule_hour * 60 + schedule_minute + agent_index * stagger_minutes
    day_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    candidate = day_start + timedelta(minutes=base_minutes)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate


def collect_one_cluster(
    database_path: Path,
    cluster_id: str,
    settings: K8sCollectorSettings | None = None,
    *,
    agent_manager=None,
) -> dict[str, int]:
    collector = settings or load_k8s_collector_settings()
    display_name = next(
        (name for cid, name in K8S_CLUSTER_SPECS if cid == cluster_id),
        cluster_id,
    )
    if agent_manager is not None:
        agent_manager.mark_agent_working(cluster_id, f"K8s 수집: {display_name}")
    try:
        snapshot = collect_cluster_snapshot(cluster_id, collector)
        counts = replace_cluster_snapshot(database_path, snapshot)
        logger.info(
            "k8s collector ok cluster=%s (%s) counts=%s",
            cluster_id,
            display_name,
            counts,
        )
        return counts
    except Exception:
        logger.exception("k8s collector failed cluster=%s (%s)", cluster_id, display_name)
        raise
    finally:
        if agent_manager is not None:
            agent_manager.mark_agent_idle(cluster_id)


def collect_all_clusters(
    database_path: Path,
    settings: K8sCollectorSettings | None = None,
    *,
    agent_manager=None,
) -> dict[str, dict[str, int]]:
    """Synchronously collect and replace inventory for every k8s agent cluster."""
    collector = settings or load_k8s_collector_settings()
    results: dict[str, dict[str, int]] = {}

    for cluster_id, _display_name in K8S_CLUSTER_SPECS:
        try:
            results[cluster_id] = collect_one_cluster(
                database_path,
                cluster_id,
                collector,
                agent_manager=agent_manager,
            )
        except Exception:
            results[cluster_id] = {}

    return results


async def _run_cluster_schedule(
    database_path: Path,
    cluster_id: str,
    agent_index: int,
    settings: K8sCollectorSettings,
    *,
    agent_manager=None,
) -> None:
    while True:
        next_at = scheduled_time_for_agent(
            agent_index,
            schedule_hour=settings.schedule_hour,
            schedule_minute=settings.schedule_minute,
            stagger_minutes=settings.stagger_minutes,
        )
        delay = max(0.0, (next_at - now_display_datetime()).total_seconds())
        logger.info(
            "k8s collector schedule cluster=%s next=%s (sleep=%.0fs)",
            cluster_id,
            next_at.isoformat(timespec="seconds"),
            delay,
        )
        await asyncio.sleep(delay)
        try:
            await asyncio.to_thread(
                collect_one_cluster,
                database_path,
                cluster_id,
                settings,
                agent_manager=agent_manager,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception(
                "k8s collector scheduled run failed cluster=%s: %s",
                cluster_id,
                exc,
            )


async def run_k8s_collector_loop(
    database_path: Path,
    settings: K8sCollectorSettings | None = None,
    *,
    agent_manager=None,
) -> None:
    collector = settings or load_k8s_collector_settings()
    if not collector.enabled:
        logger.info("k8s collector is disabled")
        return

    if not collector.collect_on_startup and not collector.schedule_enabled:
        logger.info(
            "k8s collector auto loop is paused "
            "(collect_on_startup=false, schedule_enabled=false); use manual collect API"
        )
        return

    schedule_preview = [
        (
            cluster_id,
            scheduled_time_for_agent(
                index,
                schedule_hour=collector.schedule_hour,
                schedule_minute=collector.schedule_minute,
                stagger_minutes=collector.stagger_minutes,
            ).strftime("%H:%M:%S"),
        )
        for index, (cluster_id, _) in enumerate(K8S_CLUSTER_SPECS)
    ]
    logger.info(
        "k8s collector started (daily=%02d:%02d +%smin stagger, startup=%s, schedule=%s, clusters=%s, kubeconfig=%s, slots=%s)",
        collector.schedule_hour,
        collector.schedule_minute,
        collector.stagger_minutes,
        collector.collect_on_startup,
        collector.schedule_enabled,
        len(K8S_CLUSTER_SPECS),
        collector.kubeconfig or "/etc/k8s-kubeconfig/k8s-kubeconfig",
        schedule_preview,
    )

    try:
        if collector.collect_on_startup:
            logger.info("k8s collector running startup collection for all clusters")
            try:
                await asyncio.to_thread(
                    collect_all_clusters,
                    database_path,
                    collector,
                    agent_manager=agent_manager,
                )
            except Exception as exc:
                logger.exception("k8s collector startup cycle failed: %s", exc)

        if not collector.schedule_enabled:
            logger.info("k8s collector schedule is disabled; skipping daily schedule tasks")
            return

        tasks = [
            asyncio.create_task(
                _run_cluster_schedule(
                    database_path,
                    cluster_id,
                    index,
                    collector,
                    agent_manager=agent_manager,
                ),
                name=f"k8s-collector-{cluster_id}",
            )
            for index, (cluster_id, _display_name) in enumerate(K8S_CLUSTER_SPECS)
        ]
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("k8s collector stopped")
        raise
