"""Standalone Agent Runtime FastAPI application."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.agent_runtime.api import router as runtime_router
from backend.app.agent_runtime.manager import RuntimeAgentManager
from backend.app.config import load_agent_runtime_settings, load_settings
from backend.app.db import init_database
from backend.app.logging.agent_logger import ensure_agent_logs_dir
from backend.app.logging.prompt_debug import bind_token_tracker
from backend.app.services.inventory import initialize_inventory_service
from backend.app.usage.token_tracker import TokenTracker

logger = logging.getLogger(__name__)

runtime_manager = RuntimeAgentManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    ensure_agent_logs_dir()

    llm_settings, _, _, database_path = load_settings()
    runtime_settings = load_agent_runtime_settings()

    app.state.database_path = init_database(database_path)
    inventory_service = initialize_inventory_service(database_path=app.state.database_path)
    app.state.inventory_service = inventory_service

    runtime_manager.inventory_service = inventory_service
    token_tracker = TokenTracker(max_context_tokens=llm_settings.max_context_tokens)
    bind_token_tracker(token_tracker)

    await runtime_manager.initialize(Path(app.state.database_path))
    app.state.runtime_manager = runtime_manager
    app.state.runtime_api_key = runtime_settings.api_key

    logger.info(
        "Agent runtime started (host=%s port=%s)",
        runtime_settings.host,
        runtime_settings.port,
    )
    try:
        yield
    finally:
        logger.info("Agent runtime shutting down")


def create_app() -> FastAPI:
    app = FastAPI(title="Project-A Agent Runtime", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(runtime_router)
    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = load_agent_runtime_settings()
    uvicorn.run(
        "backend.app.agent_runtime.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
