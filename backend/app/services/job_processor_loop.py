"""Poll approved jobs and delegate them to the helpdesk agent."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from uuid import uuid4

from backend.app.config import JobProcessorSettings, load_job_processor_settings
from backend.app.db.job_datetime import now_job_datetime
from backend.app.db.jobs import (
    JOB_STATUS_COMPLETED_FAILURE,
    JOB_STATUS_COMPLETED_SUCCESS,
    JOB_STATUS_DIRECT_APPROVED,
    JobRecord,
    list_jobs,
    update_job_status,
)
from backend.app.db.jobs_result import upsert_job_result
from backend.app.services.agent_runtime_client import AgentInvokeRequest, AgentRuntimeClient
from backend.app.services.job_processor import build_job_agent_message, resolve_helpdesk_agent_id

logger = logging.getLogger(__name__)


class JobProcessorState:
    def __init__(self) -> None:
        self._in_flight: set[int] = set()
        self._lock = asyncio.Lock()


async def _mark_in_flight(state: JobProcessorState, job_idx: int) -> bool:
    async with state._lock:
        if job_idx in state._in_flight:
            return False
        state._in_flight.add(job_idx)
        return True


async def _clear_in_flight(state: JobProcessorState, job_idx: int) -> None:
    async with state._lock:
        state._in_flight.discard(job_idx)


async def process_approved_job(
    database_path: Path,
    job: JobRecord,
    *,
    agent_runtime: AgentRuntimeClient,
    runtime_mode: str,
    control_plane_base_url: str | None,
    agent_manager=None,
) -> None:
    agent_id = resolve_helpdesk_agent_id(database_path, runtime_mode)
    message = build_job_agent_message(job)
    complete_date = now_job_datetime()

    if agent_manager is not None:
        agent_manager.mark_agent_working(agent_id, f"작업 처리: {job.srnum}")

    try:
        result = await agent_runtime.invoke(
            AgentInvokeRequest(
                agent_id=agent_id,
                message=message,
                trace_id=uuid4().hex,
                control_plane_base_url=control_plane_base_url,
            )
        )
        upsert_job_result(
            database_path,
            srnum=job.srnum,
            result=result.content,
            complete_date=complete_date,
        )
        update_job_status(
            database_path,
            job.idx,
            JOB_STATUS_COMPLETED_SUCCESS,
            expected_status=JOB_STATUS_DIRECT_APPROVED,
        )
        logger.info("job processor completed job idx=%s srnum=%s", job.idx, job.srnum)
    except Exception as exc:
        logger.exception("job processor failed job idx=%s srnum=%s: %s", job.idx, job.srnum, exc)
        try:
            upsert_job_result(
                database_path,
                srnum=job.srnum,
                result=f"작업 처리 실패: {exc}",
                complete_date=complete_date,
            )
            update_job_status(
                database_path,
                job.idx,
                JOB_STATUS_COMPLETED_FAILURE,
                expected_status=JOB_STATUS_DIRECT_APPROVED,
            )
        except Exception:
            logger.exception(
                "job processor failed to persist failure for idx=%s srnum=%s",
                job.idx,
                job.srnum,
            )
    finally:
        if agent_manager is not None:
            agent_manager.mark_agent_idle(agent_id)


async def _dispatch_pending_jobs(
    database_path: Path,
    *,
    agent_runtime: AgentRuntimeClient,
    runtime_mode: str,
    control_plane_base_url: str | None,
    agent_manager=None,
    state: JobProcessorState,
) -> None:
    jobs = await asyncio.to_thread(
        list_jobs,
        database_path,
        status_code=JOB_STATUS_DIRECT_APPROVED,
    )
    if not jobs:
        return

    for job in jobs:
        if not await _mark_in_flight(state, job.idx):
            continue

        async def _run(selected_job: JobRecord = job) -> None:
            try:
                await process_approved_job(
                    database_path,
                    selected_job,
                    agent_runtime=agent_runtime,
                    runtime_mode=runtime_mode,
                    control_plane_base_url=control_plane_base_url,
                    agent_manager=agent_manager,
                )
            finally:
                await _clear_in_flight(state, selected_job.idx)

        asyncio.create_task(_run(), name=f"job-processor-{job.idx}")


async def run_job_processor_loop(
    database_path: Path,
    agent_runtime: AgentRuntimeClient,
    *,
    runtime_mode: str,
    control_plane_base_url: str | None = None,
    settings: JobProcessorSettings | None = None,
    agent_manager=None,
) -> None:
    processor = settings or load_job_processor_settings()
    if not processor.enabled:
        logger.info("job processor is disabled")
        return

    state = JobProcessorState()
    if processor.initial_delay_seconds > 0:
        logger.info(
            "job processor waiting %ss before first poll",
            processor.initial_delay_seconds,
        )
        await asyncio.sleep(processor.initial_delay_seconds)

    logger.info(
        "job processor started (poll_interval=%ss, runtime_mode=%s)",
        processor.poll_interval_seconds,
        runtime_mode,
    )

    try:
        while True:
            try:
                await _dispatch_pending_jobs(
                    database_path,
                    agent_runtime=agent_runtime,
                    runtime_mode=runtime_mode,
                    control_plane_base_url=control_plane_base_url,
                    agent_manager=agent_manager,
                    state=state,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("job processor poll cycle failed: %s", exc)

            await asyncio.sleep(processor.poll_interval_seconds)
    except asyncio.CancelledError:
        logger.info("job processor stopped")
        raise
