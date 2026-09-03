"""Backend worker process: background loops only (scrape / job / mynote flush).

Run with BACKEND_ROLE=worker. Exposes /healthz for OKD probes.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.app.config import (
    load_job_decision_loop_settings,
    load_job_processor_settings,
    load_k8s_collector_settings,
    load_mynotes_settings,
    load_received_mail_settings,
    load_redis_settings,
    load_settings,
    resolve_control_plane_base_url,
)
from backend.app.db import init_database
from backend.app.services.agent_runtime_client import (
    create_agent_runtime_client,
    normalize_runtime_mode,
)
from backend.app.services.job_decision_loop import run_job_decision_loop
from backend.app.services.job_processor_loop import run_job_processor_loop
from backend.app.services.k8s_scrape_scheduler import run_k8s_scrape_scheduler_loop
from backend.app.services.mail_receive_loop import run_mail_receive_loop
from backend.app.services.mynote_flush_loop import run_mynote_flush_loop
from backend.app.services.redis_client import close_redis, init_redis

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    llm_settings, server_settings, _, database_path = load_settings()
    runtime_mode = normalize_runtime_mode(server_settings.agent_runtime_mode)
    app.state.database_path = init_database(database_path)
    app.state.agent_runtime_mode = runtime_mode
    app.state.control_plane_base_url = resolve_control_plane_base_url(server_settings)

    redis_settings = load_redis_settings()
    await init_redis(redis_settings.url)

    if runtime_mode == "mock":
        logger.warning(
            "backend-worker mock mode: agent_runtime unavailable; "
            "job processor loop will be skipped (use http mode in OKD)"
        )
        app.state.agent_runtime = None
    else:
        app.state.agent_runtime = create_agent_runtime_client(
            runtime_mode,
            agent_manager=None,
            database_path=app.state.database_path,
            http_base_url=server_settings.agent_runtime_http_base_url or None,
            http_api_key=server_settings.agent_runtime_api_key,
            http_timeout_seconds=server_settings.agent_runtime_http_timeout_seconds,
        )

    tasks: list[asyncio.Task] = []
    job_processor_settings = load_job_processor_settings()
    if job_processor_settings.enabled and app.state.agent_runtime is not None:
        tasks.append(
            asyncio.create_task(
                run_job_processor_loop(
                    Path(app.state.database_path),
                    app.state.agent_runtime,
                    runtime_mode=runtime_mode,
                    control_plane_base_url=app.state.control_plane_base_url,
                    settings=job_processor_settings,
                    agent_manager=None,
                )
            )
        )
    mynotes_settings = load_mynotes_settings()
    if mynotes_settings.enabled:
        tasks.append(
            asyncio.create_task(
                run_mynote_flush_loop(
                    Path(app.state.database_path),
                    mynotes_settings,
                )
            )
        )
    k8s_collector_settings = load_k8s_collector_settings()
    if k8s_collector_settings.schedule_enabled:
        tasks.append(
            asyncio.create_task(
                run_k8s_scrape_scheduler_loop(
                    Path(app.state.database_path),
                    runtime_mode=runtime_mode,
                    settings=k8s_collector_settings,
                )
            )
        )
    received_mail_settings = load_received_mail_settings()
    if received_mail_settings.poll_enabled:
        tasks.append(
            asyncio.create_task(
                run_mail_receive_loop(
                    Path(app.state.database_path),
                    received_mail_settings,
                )
            )
        )
    job_decision_settings = load_job_decision_loop_settings()
    if job_decision_settings.enabled:
        tasks.append(
            asyncio.create_task(
                run_job_decision_loop(
                    Path(app.state.database_path),
                    job_decision_settings,
                )
            )
        )

    logger.info(
        "backend-worker started mode=%s loops=%s",
        runtime_mode,
        len(tasks),
    )
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        await close_redis()


def create_worker_app() -> FastAPI:
    app = FastAPI(title="AX Platform Worker", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse({"status": "ok", "role": "worker"})

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        return JSONResponse({"status": "ready", "role": "worker"})

    return app


app = create_worker_app()


def run() -> None:
    import uvicorn

    _, server_settings, _, _ = load_settings()
    uvicorn.run(
        "backend.app.worker:app",
        host=server_settings.backend_host,
        port=server_settings.backend_port,
        reload=False,
    )
