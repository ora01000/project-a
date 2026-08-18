"""Standalone INFRA_GAP_ANALYSIS agent — independent of AXIT runtime and mock agent catalog."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from backend.app.agents.base import AgentInvokeResult, invoke_agent
from backend.app.config import MCPServerConfig, resolve_agent_runtime_mode
from backend.app.infra_gap_analysis.settings import (
    STATIC_CONFIG,
    http_llm_api_key,
    mcp_url_for_mode,
)
from backend.app.mcp.client import MCPClientManager
from backend.app.mcp.sanitize import wrap_tool_with_argument_sanitizer
from backend.app.services.agent_runtime_client import normalize_runtime_mode

logger = logging.getLogger(__name__)


def _build_llm(runtime_mode: str) -> ChatOpenAI:
    from backend.app.logging.prompt_debug import wrap_llm_for_prompt_debug

    if runtime_mode == "http":
        api_key = http_llm_api_key()
        if not api_key:
            raise RuntimeError(
                f"http 모드 INFRA_GAP_ANALYSIS 는 {STATIC_CONFIG.http_llm_api_key_env} 가 필요합니다."
            )
        llm: ChatOpenAI = ChatOpenAI(
            base_url=STATIC_CONFIG.http_llm_base_url,
            api_key=api_key,
            model=STATIC_CONFIG.http_llm_model,
            temperature=0,
            streaming=False,
            disable_streaming="tool_calling",
        )
    else:
        # Mock: same LLM path as the existing control-plane agents.
        from backend.app.llm.factory import get_llm

        llm = get_llm()

    return wrap_llm_for_prompt_debug(
        llm,
        agent_id=STATIC_CONFIG.agent_id,
        agent_name=STATIC_CONFIG.agent_name,
    )


class InfraGapAnalysisService:
    """In-process LangGraph agent with private MCP/LLM wiring."""

    def __init__(self) -> None:
        self._agent: Any | None = None
        self._mcp_manager: MCPClientManager | None = None
        self._runtime_mode: str = "mock"
        self._mcp_status: str = "unknown"

    @property
    def agent_id(self) -> str:
        return STATIC_CONFIG.agent_id

    @property
    def runtime_mode(self) -> str:
        return self._runtime_mode

    @property
    def mcp_status(self) -> str:
        return self._mcp_status

    @property
    def is_ready(self) -> bool:
        return self._agent is not None

    async def initialize(self, runtime_mode: str | None = None) -> None:
        mode = normalize_runtime_mode(runtime_mode or resolve_agent_runtime_mode())
        self._runtime_mode = mode
        mcp_url = mcp_url_for_mode(mode)

        servers = {
            STATIC_CONFIG.mcp_server_key: MCPServerConfig(
                transport=STATIC_CONFIG.mcp_transport,
                url=mcp_url,
                enabled=True,
            )
        }
        self._mcp_manager = MCPClientManager(servers)
        await self._mcp_manager.initialize()
        self._mcp_status = self._mcp_manager.connection_status.get(
            STATIC_CONFIG.mcp_server_key,
            "unknown",
        )

        llm = _build_llm(mode)
        tools = [
            wrap_tool_with_argument_sanitizer(tool)
            for tool in await self._mcp_manager.get_tools_for_servers(
                [STATIC_CONFIG.mcp_server_key]
            )
        ]

        prompt = STATIC_CONFIG.system_prompt
        if not tools:
            prompt = (
                f"{prompt}\n\n"
                f"The PostgreSQL MCP server ({STATIC_CONFIG.mcp_server_key} @ {mcp_url}) "
                "is not connected yet. Inform the user that the MCP endpoint is unavailable."
            )

        self._agent = create_react_agent(
            model=llm,
            tools=tools,
            prompt=SystemMessage(content=prompt),
        )
        logger.info(
            "INFRA_GAP_ANALYSIS initialized mode=%s mcp_url=%s mcp_status=%s tools=%s",
            mode,
            mcp_url,
            self._mcp_status,
            len(tools),
        )

    async def invoke(self, message: str) -> AgentInvokeResult:
        if self._agent is None:
            await self.initialize()
        assert self._agent is not None
        return await invoke_agent(
            self._agent,
            message,
            self._mcp_manager,
            agent_id=STATIC_CONFIG.agent_id,
            agent_name=STATIC_CONFIG.agent_name,
            mcp_server_keys=[STATIC_CONFIG.mcp_server_key],
        )

    def status(self) -> dict[str, Any]:
        return {
            "agent_id": STATIC_CONFIG.agent_id,
            "agent_name": STATIC_CONFIG.agent_name,
            "ready": self.is_ready,
            "runtime_mode": self._runtime_mode,
            "mcp_server_key": STATIC_CONFIG.mcp_server_key,
            "mcp_url": mcp_url_for_mode(self._runtime_mode),
            "mcp_status": self._mcp_status,
            "llm": (
                {
                    "base_url": STATIC_CONFIG.http_llm_base_url,
                    "model": STATIC_CONFIG.http_llm_model,
                }
                if self._runtime_mode == "http"
                else {"source": "control-plane-existing-llm"}
            ),
        }


infra_gap_analysis_service = InfraGapAnalysisService()
