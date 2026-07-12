import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from typing import Any

from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.agents.base import AgentDefinition, _aggregate_mcp_status, build_agent
from backend.app.agents.inventory_agent import INVENTORY_AGENT_MARKER
from backend.app.agents.inventory_tool import INVENTORY_AGENT_ID
from backend.app.agents.registry import load_agent_definitions
from backend.app.api.agent_logs import router as agent_logs_router
from backend.app.api.agent_records import router as agent_records_router
from backend.app.api.agents import router as agents_router
from backend.app.api.auth import router as auth_router
from backend.app.api.chat import router as chat_router
from backend.app.api.inventory import router as inventory_router
from backend.app.api.jobs import router as jobs_router
from backend.app.api.signup import router as signup_router
from backend.app.api.users import router as users_router
from backend.app.api.whatap_webhook import router as whatap_webhook_router
from backend.app.config import load_settings
from backend.app.db import init_database
from backend.app.logging.agent_logger import ensure_agent_logs_dir, log_agent_error
from backend.app.logging.user_comm_logger import initialize_user_comm_logs
from backend.app.mcp.client import MCPClientManager
from backend.app.services.inventory import initialize_inventory_service
from backend.app.usage.token_tracker import TokenTracker

logger = logging.getLogger(__name__)


class AgentManager:
    def __init__(self) -> None:
        self.agents: dict[str, Any] = {}
        self.agent_definitions: list[AgentDefinition] = []
        self.agent_definitions_by_id: dict[str, AgentDefinition] = {}
        self.agent_operation_status: dict[str, str] = {}
        self.agent_operation_errors: dict[str, str] = {}
        self.agent_active_counts: dict[str, int] = {}
        self.agent_health_status: dict[str, str] = {}
        self.mcp_manager: MCPClientManager | None = None
        self.llm_status: str = "unknown"
        self.token_tracker: TokenTracker | None = None
        self.max_context_tokens: int = 32768
        self._health_check_lock = asyncio.Lock()

    async def initialize(self, database_path: Path) -> None:
        llm_settings, _, mcp_servers, _ = load_settings()
        self.max_context_tokens = llm_settings.max_context_tokens
        self.token_tracker = TokenTracker(max_context_tokens=self.max_context_tokens)
        self.mcp_manager = MCPClientManager(mcp_servers)
        await self.mcp_manager.initialize()

        self.agent_definitions = load_agent_definitions(database_path)
        self.agent_definitions_by_id = {
            definition.agent_id: definition for definition in self.agent_definitions
        }

        for definition in self.agent_definitions:
            self.agent_operation_status.setdefault(definition.agent_id, "idle")
            self.agent_active_counts.setdefault(definition.agent_id, 0)
            if definition.agent_id == INVENTORY_AGENT_ID:
                self.agents[definition.agent_id] = INVENTORY_AGENT_MARKER
                continue
            try:
                self.agents[definition.agent_id] = await build_agent(definition, self.mcp_manager)
            except Exception as exc:
                self.mark_agent_error(
                    definition.agent_id,
                    f"Agent build failed: {exc}",
                )

        self.llm_status = await self._check_llm(llm_settings.base_url)
        self._refresh_agent_health_status()

    async def refresh_health(self) -> None:
        async with self._health_check_lock:
            llm_settings, _, _, _ = load_settings()
            self.llm_status = await self._check_llm(llm_settings.base_url)
            if self.mcp_manager is not None:
                await self.mcp_manager.refresh_health()
            self._refresh_agent_health_status()

    def _refresh_agent_health_status(self) -> None:
        statuses: dict[str, str] = {}
        for definition in self.agent_definitions:
            agent_id = definition.agent_id
            if agent_id == INVENTORY_AGENT_ID:
                statuses[agent_id] = self.get_inventory_health_status()
                continue
            if agent_id not in self.agents:
                statuses[agent_id] = "unavailable"
                continue
            if self.mcp_manager is None:
                statuses[agent_id] = "unknown"
                continue
            statuses[agent_id] = _aggregate_mcp_status(
                self.mcp_manager,
                definition.mcp_server_keys,
            )
        self.agent_health_status = statuses

    def get_agent_health_status(self) -> dict[str, str]:
        return dict(self.agent_health_status)

    def get_inventory_health_status(self) -> str:
        inventory_service = getattr(self, "inventory_service", None)
        if inventory_service is None:
            return "unknown"
        return inventory_service.status

    async def reload_agents(self, database_path: Path) -> None:
        if self.mcp_manager is None:
            raise RuntimeError("AgentManager is not initialized")

        self.agent_definitions = load_agent_definitions(database_path)
        self.agent_definitions_by_id = {
            definition.agent_id: definition for definition in self.agent_definitions
        }

        next_agent_ids = {definition.agent_id for definition in self.agent_definitions}
        for agent_id in list(self.agents.keys()):
            if agent_id not in next_agent_ids:
                del self.agents[agent_id]
        for agent_id in list(self.agent_operation_status.keys()):
            if agent_id not in next_agent_ids:
                del self.agent_operation_status[agent_id]
                self.agent_operation_errors.pop(agent_id, None)
                self.agent_active_counts.pop(agent_id, None)

        for definition in self.agent_definitions:
            self.agent_operation_status.setdefault(definition.agent_id, "idle")
            self.agent_active_counts.setdefault(definition.agent_id, 0)
            if definition.agent_id == INVENTORY_AGENT_ID:
                self.agents[definition.agent_id] = INVENTORY_AGENT_MARKER
                continue
            try:
                self.agents[definition.agent_id] = await build_agent(definition, self.mcp_manager)
                if self.agent_operation_status.get(definition.agent_id) == "error":
                    self.agent_operation_status[definition.agent_id] = "idle"
                    self.agent_operation_errors.pop(definition.agent_id, None)
            except Exception as exc:
                self.mark_agent_error(
                    definition.agent_id,
                    f"Agent rebuild failed: {exc}",
                )

        self._refresh_agent_health_status()

    async def _check_llm(self, base_url: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{base_url.rstrip('/')}/models")
                if response.status_code < 500:
                    return "connected"
                return f"error: HTTP {response.status_code}"
        except Exception as exc:
            return f"error: {exc}"

    def get_agent(self, agent_id: str) -> Any:
        if agent_id not in self.agents:
            raise KeyError(agent_id)
        return self.agents[agent_id]

    def get_definition(self, agent_id: str) -> AgentDefinition:
        if agent_id not in self.agent_definitions_by_id:
            raise KeyError(agent_id)
        return self.agent_definitions_by_id[agent_id]

    def get_operation_status(self, agent_id: str) -> str:
        return self.agent_operation_status.get(agent_id, "idle")

    def get_operation_error(self, agent_id: str) -> str | None:
        return self.agent_operation_errors.get(agent_id)

    def mark_agent_working(self, agent_id: str) -> None:
        self.agent_active_counts[agent_id] = self.agent_active_counts.get(agent_id, 0) + 1
        self.agent_operation_status[agent_id] = "working"
        self.agent_operation_errors.pop(agent_id, None)

    def mark_agent_idle(self, agent_id: str) -> None:
        active_count = max(0, self.agent_active_counts.get(agent_id, 0) - 1)
        self.agent_active_counts[agent_id] = active_count
        if active_count == 0 and self.agent_operation_status.get(agent_id) != "error":
            self.agent_operation_status[agent_id] = "idle"

    def mark_agent_error(
        self,
        agent_id: str,
        reason: str,
        *,
        input_message: str | None = None,
    ) -> None:
        self.agent_active_counts[agent_id] = 0
        self.agent_operation_status[agent_id] = "error"
        self.agent_operation_errors[agent_id] = reason
        log_agent_error(agent_id, reason=reason, input_message=input_message)


agent_manager = AgentManager()


async def _health_check_loop(manager: AgentManager, interval_seconds: int) -> None:
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await manager.refresh_health()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.exception("Periodic health check failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    ensure_agent_logs_dir()
    initialize_user_comm_logs()
    _, server_settings, _, database_path = load_settings()
    app.state.database_path = init_database(database_path)
    inventory_service = initialize_inventory_service()
    app.state.inventory_service = inventory_service
    await agent_manager.initialize(app.state.database_path)
    agent_manager.inventory_service = inventory_service
    agent_manager._refresh_agent_health_status()
    app.state.agent_manager = agent_manager

    health_task = asyncio.create_task(
        _health_check_loop(
            agent_manager,
            server_settings.health_check_interval_seconds,
        )
    )
    try:
        yield
    finally:
        health_task.cancel()
        with suppress(asyncio.CancelledError):
            await health_task


def create_app() -> FastAPI:
    app = FastAPI(title="LangGraph Multi-Agent API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_router, prefix="/api")
    app.include_router(signup_router, prefix="/api")
    app.include_router(users_router, prefix="/api")
    app.include_router(agent_logs_router, prefix="/api")
    app.include_router(agent_records_router, prefix="/api")
    app.include_router(agents_router, prefix="/api")
    app.include_router(jobs_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")
    app.include_router(inventory_router, prefix="/api")
    app.include_router(whatap_webhook_router, prefix="/api")
    return app


app = create_app()


def run() -> None:
    import uvicorn

    _, server_settings, _, _ = load_settings()
    uvicorn.run(
        "backend.app.main:app",
        host=server_settings.backend_host,
        port=server_settings.backend_port,
        reload=True,
    )
