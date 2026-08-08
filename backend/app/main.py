import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from typing import Any

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.agents.base import AgentDefinition, _aggregate_mcp_status, build_agent
from backend.app.agents.mock_platform_agents import is_mock_platform_orchestrator_agent
from backend.app.agents.orchestrator_agent import ORCHESTRATOR_MARKER
from backend.app.agents.remote_agent import REMOTE_AGENT_MARKER
from backend.app.mcp.client import MCPClientManager
from backend.app.agents.registry import load_mock_runtime_definitions, load_server_agent_definitions
from backend.app.agents.system_agents import is_control_plane_orchestration_agent
from backend.app.api.agent_logs import router as agent_logs_router
from backend.app.api.agentruntime_records import router as agentruntime_records_router
from backend.app.api.agents import router as agents_router
from backend.app.api.auth import router as auth_router
from backend.app.api.chat import router as chat_router
from backend.app.api.debug import router as debug_router
from backend.app.api.jobs import router as jobs_router
from backend.app.api.llm import router as llm_router
from backend.app.api.notices import router as notices_router
from backend.app.api.mock_llm import router as mock_llm_router
from backend.app.api.mynotes import router as mynotes_router
from backend.app.api.postman_debug import router as postman_debug_router
from backend.app.api.release import router as release_router
from backend.app.api.signup import router as signup_router
from backend.app.api.users import router as users_router
from backend.app.api.teams_inbound_debug import router as teams_inbound_debug_router
from backend.app.api.whatap_test import router as whatap_test_router
from backend.app.api.whatap_webhook import router as whatap_webhook_router
from backend.app.api.axit_mock import router as axit_mock_router
from backend.app.api.k8s_infra import router as k8s_infra_router
from backend.app.api.sqlite_pg_migrate import router as sqlite_pg_migrate_router
from backend.app.config import (
    load_auth_session_settings,
    load_job_processor_settings,
    load_k8s_collector_settings,
    load_mynotes_settings,
    load_redis_settings,
    load_settings,
    resolve_control_plane_base_url,
)
from backend.app.middleware.session_auth import SessionAuthMiddleware
from backend.app.services.redis_client import close_redis, init_redis
from backend.app.services.agent_runtime_client import (
    create_agent_runtime_client,
    get_runtime_capabilities,
    normalize_runtime_mode,
)
from backend.app.db import init_database
from backend.app.disabled_features import filter_agent_definitions
from backend.app.logging.prompt_debug import bind_token_tracker
from backend.app.logging.agent_logger import ensure_agent_logs_dir, log_agent_error
from backend.app.logging.user_comm_logger import initialize_user_comm_logs
from backend.app.services.job_processor_loop import run_job_processor_loop
from backend.app.services.k8s_scrape_scheduler import run_k8s_scrape_scheduler_loop
from backend.app.services.mynote_flush_loop import run_mynote_flush_loop
from backend.app.usage.token_tracker import TokenTracker

logger = logging.getLogger(__name__)


class AgentManager:
    def __init__(self) -> None:
        self.agents: dict[str, Any] = {}
        self.agent_definitions: list[AgentDefinition] = []
        self.system_agent_definitions: list[AgentDefinition] = []
        self.agent_definitions_by_id: dict[str, AgentDefinition] = {}
        self.agent_operation_status: dict[str, str] = {}
        self.agent_operation_errors: dict[str, str] = {}
        self.agent_operation_tasks: dict[str, dict[str, str]] = {}
        self.agent_active_counts: dict[str, int] = {}
        self.agent_health_status: dict[str, str] = {}
        self._agent_invoke_failures: set[str] = set()
        self.mcp_manager = None
        self.token_tracker: TokenTracker | None = None
        self.max_context_tokens: int = 32768
        self.execution_mode: str = "mock"
        self.agent_runtime: Any | None = None
        self._runtime_health_cache: dict[str, Any] = {}
        self._health_check_lock = asyncio.Lock()

    def _register_system_agents(self) -> None:
        self.system_agent_definitions = []

    def _register_db_agents(self) -> None:
        for definition in self.agent_definitions:
            if definition.agent_id not in self.agents:
                self.agent_operation_status.setdefault(definition.agent_id, "idle")
                self.agent_active_counts.setdefault(definition.agent_id, 0)
                if self.uses_remote_runtime():
                    self.agents[definition.agent_id] = REMOTE_AGENT_MARKER

    async def _build_local_agents(self) -> None:
        _, _, mcp_servers, _ = load_settings()
        if self.mcp_manager is None:
            self.mcp_manager = MCPClientManager(mcp_servers)
            await self.mcp_manager.initialize()

        next_agent_ids = {definition.agent_id for definition in self.agent_definitions}
        for agent_id in list(self.agents.keys()):
            if agent_id not in next_agent_ids:
                del self.agents[agent_id]

        for definition in self.agent_definitions:
            try:
                if is_mock_platform_orchestrator_agent(definition.agent_id):
                    self.agents[definition.agent_id] = ORCHESTRATOR_MARKER
                    continue
                self.agents[definition.agent_id] = await build_agent(definition, self.mcp_manager)
            except Exception as exc:
                logger.exception("Failed to build agent %s: %s", definition.agent_id, exc)
                self.agents.pop(definition.agent_id, None)

    def _load_runtime_definitions(self, database_path: Path) -> list[AgentDefinition]:
        if self.uses_remote_runtime():
            return filter_agent_definitions(load_server_agent_definitions(database_path))
        return filter_agent_definitions(load_mock_runtime_definitions(database_path))

    async def initialize(self, database_path: Path, *, execution_mode: str = "mock") -> None:
        self.execution_mode = normalize_runtime_mode(execution_mode)
        llm_settings, _, _, _ = load_settings()
        self.max_context_tokens = llm_settings.max_context_tokens
        self.token_tracker = TokenTracker(max_context_tokens=self.max_context_tokens)
        bind_token_tracker(self.token_tracker)

        self.agent_definitions = self._load_runtime_definitions(database_path)
        self.agent_definitions_by_id = {
            definition.agent_id: definition for definition in self.agent_definitions
        }
        self._register_db_agents()
        self._register_system_agents()
        if not self.uses_remote_runtime():
            await self._build_local_agents()
        await self.refresh_health()

    async def refresh_health(self) -> None:
        async with self._health_check_lock:
            if self.agent_runtime is not None and get_runtime_capabilities(self.execution_mode).health_summary:
                try:
                    self._runtime_health_cache = await self.agent_runtime.get_runtime_summary()
                except Exception as exc:
                    logger.exception("Failed to refresh sandbox runtime health: %s", exc)
                    self._runtime_health_cache = {}
            else:
                self._runtime_health_cache = {}
            self._refresh_agent_health_status()

    def uses_remote_runtime(self) -> bool:
        return self.execution_mode == "http"

    def _refresh_agent_health_status(self) -> None:
        remote_status = self._runtime_health_cache.get("agent_status", {})
        use_mock_fallback = not get_runtime_capabilities(self.execution_mode).health_summary
        statuses: dict[str, str] = {}
        for definition in self.agent_definitions:
            agent_id = definition.agent_id
            if agent_id not in self.agents:
                statuses[agent_id] = "unavailable"
                continue
            if is_control_plane_orchestration_agent(agent_id):
                statuses[agent_id] = "ready"
                continue
            if is_mock_platform_orchestrator_agent(agent_id):
                statuses[agent_id] = "ready"
                continue
            if self.uses_remote_runtime():
                statuses[agent_id] = self.get_axit_agent_connection_status(agent_id)
                continue
            if use_mock_fallback:
                if (
                    self.mcp_manager is not None
                    and self.agents.get(agent_id) is not REMOTE_AGENT_MARKER
                ):
                    statuses[agent_id] = _aggregate_mcp_status(
                        self.mcp_manager,
                        definition.mcp_server_keys,
                    )
                else:
                    statuses[agent_id] = "mock"
                continue
            if isinstance(remote_status, dict) and agent_id in remote_status:
                statuses[agent_id] = str(remote_status[agent_id])
            else:
                statuses[agent_id] = "unknown"
        self.agent_health_status = statuses

    def get_agent_health_status(self) -> dict[str, str]:
        return dict(self.agent_health_status)

    def get_runtime_status(self) -> str:
        statuses = list(self.agent_health_status.values())
        if not statuses:
            return "unknown"

        active_statuses = [status for status in statuses if status != "unavailable"]
        if not active_statuses:
            return "unavailable"
        if all(status in {"connected", "ready", "mock"} for status in active_statuses):
            return "connected"
        if any(status in {"connected", "partial", "ready", "degraded"} for status in active_statuses):
            return "partial"
        return active_statuses[0]

    def sync_remote_catalog(self, database_path: Path) -> None:
        """Refresh http-mode agent catalog and health badges from DB without MCP rebuild."""
        if not self.uses_remote_runtime():
            return

        self.agent_definitions = self._load_runtime_definitions(database_path)
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
                self.agent_operation_tasks.pop(agent_id, None)
        self._agent_invoke_failures = {
            agent_id for agent_id in self._agent_invoke_failures if agent_id in next_agent_ids
        }

        self._register_db_agents()
        self._register_system_agents()
        self._refresh_agent_health_status()

    async def reload_agents(self, database_path: Path) -> None:
        self.agent_definitions = self._load_runtime_definitions(database_path)
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
                self.agent_operation_tasks.pop(agent_id, None)
        self._agent_invoke_failures = {
            agent_id for agent_id in self._agent_invoke_failures if agent_id in next_agent_ids
        }

        self._register_db_agents()
        self._register_system_agents()
        if not self.uses_remote_runtime():
            await self._build_local_agents()
        await self.refresh_health()

    async def rebuild_langgraph_agents(self) -> None:
        """Rebuild LangGraph agents so runtime LLM provider changes take effect."""
        if self.uses_remote_runtime() or self.mcp_manager is None:
            return

        for definition in self.agent_definitions:
            agent_id = definition.agent_id
            if is_mock_platform_orchestrator_agent(agent_id):
                continue
            current = self.agents.get(agent_id)
            if current in (REMOTE_AGENT_MARKER, ORCHESTRATOR_MARKER):
                continue
            try:
                self.agents[agent_id] = await build_agent(definition, self.mcp_manager)
            except Exception as exc:
                logger.exception("Failed to rebuild agent %s after LLM change: %s", agent_id, exc)
                self.agents.pop(agent_id, None)

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

    def get_operation_detail(self, agent_id: str) -> str | None:
        details = self.get_operation_details(agent_id)
        if not details:
            return None
        return details[0]

    def get_operation_details(self, agent_id: str) -> list[str]:
        tasks = self.agent_operation_tasks.get(agent_id)
        if not tasks:
            return []
        return list(tasks.values())

    def get_active_count(self, agent_id: str) -> int:
        return len(self.agent_operation_tasks.get(agent_id, {}))

    def _sync_operation_state(self, agent_id: str) -> None:
        count = len(self.agent_operation_tasks.get(agent_id, {}))
        self.agent_active_counts[agent_id] = count
        if count > 0:
            self.agent_operation_status[agent_id] = "working"
            return
        if self.agent_operation_status.get(agent_id) != "error":
            self.agent_operation_status[agent_id] = "idle"

    def mark_agent_working(
        self,
        agent_id: str,
        detail: str | None = None,
        *,
        task_id: str | None = None,
    ) -> str:
        from uuid import uuid4

        key = (task_id or "").strip() or uuid4().hex
        label = (detail or "").strip() or "처리 중"
        tasks = self.agent_operation_tasks.setdefault(agent_id, {})
        tasks[key] = label
        self.agent_operation_errors.pop(agent_id, None)
        self._sync_operation_state(agent_id)
        return key

    def mark_agent_idle(self, agent_id: str, task_id: str | None = None) -> None:
        tasks = self.agent_operation_tasks.get(agent_id)
        if tasks:
            if task_id and task_id in tasks:
                del tasks[task_id]
            elif not task_id and tasks:
                last_key = next(reversed(tasks))
                del tasks[last_key]
            if not tasks:
                self.agent_operation_tasks.pop(agent_id, None)
        self._sync_operation_state(agent_id)

    def get_axit_agent_connection_status(self, agent_id: str) -> str:
        """AXIT lambda agents are assumed alive unless invoke has ever failed."""
        if agent_id in self._agent_invoke_failures:
            return "degraded"
        return "connected"

    def mark_agent_invoke_failure(self, agent_id: str, reason: str) -> None:
        if agent_id not in self._agent_invoke_failures:
            logger.warning("Agent %s invoke failure latched (degraded): %s", agent_id, reason)
        self._agent_invoke_failures.add(agent_id)
        if self.uses_remote_runtime() and agent_id in self.agents:
            self.agent_health_status[agent_id] = "degraded"

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
        self.agent_operation_tasks.pop(agent_id, None)
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
    runtime_mode = normalize_runtime_mode(server_settings.agent_runtime_mode)
    logger.info("AGENT_RUNTIME_MODE=%s", runtime_mode)
    logger.info(
        "AGENT_RUNTIME_HTTP_TIMEOUT_SECONDS=%s",
        server_settings.agent_runtime_http_timeout_seconds,
    )
    app.state.database_path = init_database(database_path)
    if runtime_mode == "mock":
        from backend.app.services.mock_llm_runtime import load_persisted_runtime_state

        load_persisted_runtime_state()
    await agent_manager.initialize(
        app.state.database_path,
        execution_mode=runtime_mode,
    )
    app.state.agent_manager = agent_manager
    app.state.agent_runtime_mode = runtime_mode
    app.state.control_plane_base_url = resolve_control_plane_base_url(server_settings)
    app.state.runtime_api_key = server_settings.agent_runtime_api_key
    redis_settings = load_redis_settings()
    await init_redis(redis_settings.url)
    app.state.auth_session_settings = load_auth_session_settings()
    app.state.agent_runtime = create_agent_runtime_client(
        runtime_mode,
        agent_manager=agent_manager,
        database_path=app.state.database_path,
        http_base_url=server_settings.agent_runtime_http_base_url or None,
        http_api_key=server_settings.agent_runtime_api_key,
        http_timeout_seconds=server_settings.agent_runtime_http_timeout_seconds,
    )
    agent_manager.agent_runtime = app.state.agent_runtime

    health_task = asyncio.create_task(
        _health_check_loop(
            agent_manager,
            server_settings.health_check_interval_seconds,
        )
    )
    job_processor_settings = load_job_processor_settings()
    job_processor_task: asyncio.Task | None = None
    if job_processor_settings.enabled:
        job_processor_task = asyncio.create_task(
            run_job_processor_loop(
                Path(app.state.database_path),
                app.state.agent_runtime,
                runtime_mode=runtime_mode,
                control_plane_base_url=app.state.control_plane_base_url,
                settings=job_processor_settings,
                agent_manager=agent_manager,
            )
        )
    mynotes_settings = load_mynotes_settings()
    mynote_flush_task: asyncio.Task | None = None
    if mynotes_settings.enabled:
        mynote_flush_task = asyncio.create_task(
            run_mynote_flush_loop(
                Path(app.state.database_path),
                mynotes_settings,
            )
        )
    k8s_collector_settings = load_k8s_collector_settings()
    k8s_scrape_task: asyncio.Task | None = None
    if k8s_collector_settings.schedule_enabled:
        k8s_scrape_task = asyncio.create_task(
            run_k8s_scrape_scheduler_loop(
                Path(app.state.database_path),
                runtime_mode=runtime_mode,
                settings=k8s_collector_settings,
            )
        )
    try:
        yield
    finally:
        health_task.cancel()
        with suppress(asyncio.CancelledError):
            await health_task
        if job_processor_task is not None:
            job_processor_task.cancel()
            with suppress(asyncio.CancelledError):
                await job_processor_task
        if mynote_flush_task is not None:
            mynote_flush_task.cancel()
            with suppress(asyncio.CancelledError):
                await mynote_flush_task
        if k8s_scrape_task is not None:
            k8s_scrape_task.cancel()
            with suppress(asyncio.CancelledError):
                await k8s_scrape_task
        await close_redis()


def create_app() -> FastAPI:
    app = FastAPI(title="LangGraph Multi-Agent API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SessionAuthMiddleware)
    app.include_router(auth_router, prefix="/api")
    app.include_router(signup_router, prefix="/api")
    app.include_router(users_router, prefix="/api")
    app.include_router(agent_logs_router, prefix="/api")
    app.include_router(agentruntime_records_router, prefix="/api")
    app.include_router(agents_router, prefix="/api")
    app.include_router(jobs_router, prefix="/api")
    app.include_router(mynotes_router, prefix="/api")
    app.include_router(notices_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")
    app.include_router(llm_router, prefix="/api")
    app.include_router(debug_router, prefix="/api")
    app.include_router(postman_debug_router, prefix="/api")
    app.include_router(mock_llm_router, prefix="/api")
    app.include_router(release_router, prefix="/api")
    app.include_router(teams_inbound_debug_router, prefix="/api")
    app.include_router(whatap_webhook_router, prefix="/api")
    app.include_router(whatap_test_router, prefix="/api")
    app.include_router(k8s_infra_router, prefix="/api")
    app.include_router(sqlite_pg_migrate_router, prefix="/api")
    app.include_router(axit_mock_router)
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
