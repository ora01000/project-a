"""Periodic job-requester simulator for testing the job planning agent.

This is not an agent. It randomly selects code-managed READ-only samples and
submits them through the existing job-request pipeline.
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import date, timedelta
from pathlib import Path

from backend.app.agents.system_agents import JOB_PLANNING_AGENT_ID, NotifyChannel
from backend.app.config import JobRequesterSettings, load_job_requester_settings
from backend.app.services.job_planning import submit_job_request
from backend.app.testing.job_request_samples import (
    JOB_REQUEST_SAMPLES,
    REQUEST_DEPART,
    REQUESTER,
    REQUESTER_EMAIL,
    JobRequestSample,
)

logger = logging.getLogger(__name__)


class JobRequester:
    def __init__(
        self,
        database_path: Path,
        settings: JobRequesterSettings | None = None,
        *,
        agent_manager=None,
    ) -> None:
        self.database_path = database_path
        self.settings = settings or load_job_requester_settings()
        self.agent_manager = agent_manager
        self._last_sample_id: str | None = None
        self._dispatch_count = 0

    @property
    def enabled(self) -> bool:
        return self.settings.enabled

    @property
    def dispatch_count(self) -> int:
        return self._dispatch_count

    def _pick_sample(self) -> JobRequestSample:
        candidates = list(JOB_REQUEST_SAMPLES)
        if len(candidates) > 1 and self._last_sample_id is not None:
            candidates = [sample for sample in candidates if sample.sample_id != self._last_sample_id]
        if not candidates:
            candidates = list(JOB_REQUEST_SAMPLES)
        sample = random.choice(candidates)
        self._last_sample_id = sample.sample_id
        return sample

    async def dispatch_once(self) -> JobRequestSample:
        sample = self._pick_sample()
        today = date.today()
        request_date = today.isoformat()
        completion_request_date = (today + timedelta(days=3)).isoformat()

        if self.agent_manager is not None:
            self.agent_manager.mark_agent_working(JOB_PLANNING_AGENT_ID)

        try:
            job = await submit_job_request(
                self.database_path,
                request_date=request_date,
                job_title=sample.job_title,
                request_depart=REQUEST_DEPART,
                requester=REQUESTER,
                requester_email=REQUESTER_EMAIL,
                completion_request_date=completion_request_date,
                job_description=sample.job_description,
                approver=sample.approver,
                notify_channel=NotifyChannel.INTEGRATED_CHAT,
            )
            self._dispatch_count += 1
            logger.info(
                "Job requester dispatched sample=%s job_idx=%s title=%s approver=%s family=%s",
                sample.sample_id,
                job.idx,
                sample.job_title,
                sample.approver,
                sample.target_agent_family,
            )
            return sample
        except Exception:
            if self.agent_manager is not None:
                self.agent_manager.mark_agent_error(
                    JOB_PLANNING_AGENT_ID,
                    "Job requester dispatch failed",
                    input_message=sample.job_title,
                )
            raise
        finally:
            if self.agent_manager is not None:
                self.agent_manager.mark_agent_idle(JOB_PLANNING_AGENT_ID)


async def run_job_requester_loop(
    database_path: Path,
    settings: JobRequesterSettings | None = None,
    *,
    agent_manager=None,
) -> None:
    requester_settings = settings or load_job_requester_settings()
    if not requester_settings.enabled:
        logger.info("Job requester is disabled")
        return

    requester = JobRequester(
        database_path,
        requester_settings,
        agent_manager=agent_manager,
    )
    interval_seconds = requester_settings.interval_minutes * 60
    logger.info(
        "Job requester started (interval=%s min, initial_delay=%s sec, samples=%s)",
        requester_settings.interval_minutes,
        requester_settings.initial_delay_seconds,
        len(JOB_REQUEST_SAMPLES),
    )

    try:
        if requester_settings.initial_delay_seconds > 0:
            await asyncio.sleep(requester_settings.initial_delay_seconds)

        while True:
            try:
                await requester.dispatch_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Job requester dispatch failed: %s", exc)

            await asyncio.sleep(interval_seconds)
    except asyncio.CancelledError:
        logger.info("Job requester stopped (dispatched=%s)", requester.dispatch_count)
        raise
