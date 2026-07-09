import logging
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.agents.base import build_agent
from backend.app.agents.registry import AGENT_DEFINITIONS, AGENT_DEFINITIONS_BY_ID
from backend.app.api.agents import router as agents_router
from backend.app.api.auth import router as auth_router
from backend.app.api.chat import router as chat_router
from backend.app.api.users import router as users_router
from backend.app.config import load_settings
from backend.app.db import init_database
from backend.app.logging.agent_logger import ensure_agent_logs_dir
from backend.app.mcp.client import MCPClientManager
from backend.app.usage.token_tracker import TokenTracker

logger = logging.getLogger(__name__)


class AgentManager:
    def __init__(self) -> None:
        self.agents: dict[str, Any] = {}
        self.mcp_manager: MCPClientManager | None = None
        self.llm_status: str = "unknown"
        self.token_tracker: TokenTracker | None = None
        self.max_context_tokens: int = 32768

    async def initialize(self) -> None:
        llm_settings, _, mcp_servers, _ = load_settings()
        self.max_context_tokens = llm_settings.max_context_tokens
        self.token_tracker = TokenTracker(max_context_tokens=self.max_context_tokens)
        self.mcp_manager = MCPClientManager(mcp_servers)
        await self.mcp_manager.initialize()

        for definition in AGENT_DEFINITIONS:
            self.agents[definition.agent_id] = await build_agent(definition, self.mcp_manager)

        self.llm_status = await self._check_llm(llm_settings.base_url)

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

    def get_definition(self, agent_id: str):
        return AGENT_DEFINITIONS_BY_ID[agent_id]


agent_manager = AgentManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    ensure_agent_logs_dir()
    _, _, _, database_path = load_settings()
    app.state.database_path = init_database(database_path)
    await agent_manager.initialize()
    app.state.agent_manager = agent_manager
    yield


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
    app.include_router(users_router, prefix="/api")
    app.include_router(agents_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")
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
