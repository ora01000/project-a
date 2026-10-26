"""JOB_REQUEST_HELPER — mock: in-process LangGraph; http: external AXIT via agentruntime."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from backend.app.agents.base import AgentInvokeResult, invoke_agent
from backend.app.config import _env_setting, load_settings, resolve_agent_runtime_mode
from backend.app.job_request_helper.settings import MCP_SERVER_KEYS, STATIC_CONFIG, build_system_prompt
from backend.app.mcp.client import MCPClientManager
from backend.app.mcp.sanitize import wrap_tool_with_argument_sanitizer
from backend.app.services.agent_runtime_client import AgentInvokeRequest, normalize_runtime_mode

logger = logging.getLogger(__name__)


def _build_llm(runtime_mode: str) -> ChatOpenAI:
    from backend.app.logging.prompt_debug import wrap_llm_for_prompt_debug

    if runtime_mode == "http":
        api_key = _env_setting(STATIC_CONFIG.http_llm_api_key_env)
        if not api_key:
            raise RuntimeError(
                f"http 모드 JOB_REQUEST_HELPER 는 {STATIC_CONFIG.http_llm_api_key_env} 가 필요합니다."
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
        from backend.app.llm.factory import get_llm

        llm = get_llm()

    return wrap_llm_for_prompt_debug(
        llm,
        agent_id=STATIC_CONFIG.agent_id,
        agent_name=STATIC_CONFIG.agent_name,
    )


class JobRequestHelperService:
    """mock: PRIVATE_CLOUD tools+skills in-process. http: AXIT via agentruntime."""

    def __init__(self) -> None:
        self._agent: Any | None = None
        self._runtime_mode: str = "mock"
        self._agent_runtime: Any | None = None
        self._mcp_manager: MCPClientManager | None = None
        self._owns_mcp_manager: bool = False
        self._tool_names: list[str] = []

    @property
    def agent_id(self) -> str:
        return STATIC_CONFIG.agent_id

    @property
    def is_ready(self) -> bool:
        if self._runtime_mode == "http":
            return self._agent_runtime is not None
        return self._agent is not None

    def bind_agent_runtime(self, agent_runtime: Any | None, runtime_mode: str) -> None:
        self._runtime_mode = normalize_runtime_mode(runtime_mode)
        self._agent_runtime = agent_runtime

    async def initialize(
        self,
        runtime_mode: str | None = None,
        *,
        mcp_manager: MCPClientManager | None = None,
    ) -> None:
        mode = normalize_runtime_mode(runtime_mode or resolve_agent_runtime_mode())
        self._runtime_mode = mode
        if mode == "http":
            logger.info(
                "JOB_REQUEST_HELPER http mode: skip in-process init "
                "(use agentruntime local_agent_id=%s)",
                STATIC_CONFIG.agent_id,
            )
            self._agent = None
            self._mcp_manager = None
            self._owns_mcp_manager = False
            self._tool_names = []
            return

        if mcp_manager is not None:
            self._mcp_manager = mcp_manager
            self._owns_mcp_manager = False
        else:
            _, _, mcp_servers, _ = load_settings()
            filtered = {
                key: config
                for key, config in mcp_servers.items()
                if key in MCP_SERVER_KEYS
            }
            self._mcp_manager = MCPClientManager(filtered)
            await self._mcp_manager.initialize()
            self._owns_mcp_manager = True

        llm = _build_llm(mode)
        tools = [
            wrap_tool_with_argument_sanitizer(tool)
            for tool in await self._mcp_manager.get_tools_for_servers(MCP_SERVER_KEYS)
        ]
        self._tool_names = [tool.name for tool in tools]

        prompt = build_system_prompt()
        if not tools:
            server_keys = ", ".join(MCP_SERVER_KEYS)
            prompt = (
                f"{prompt}\n\n"
                f"The MCP server(s) for PRIVATE_CLOUD_AGENT ({server_keys}) "
                "are not connected yet. Still draft the request form from the given "
                "key=value context without inventing live inventory facts."
            )

        self._agent = create_react_agent(
            model=llm,
            tools=tools,
            prompt=SystemMessage(content=prompt),
        )
        logger.info(
            "JOB_REQUEST_HELPER initialized mode=%s mcp_keys=%s tools=%s tool_names=%s",
            mode,
            MCP_SERVER_KEYS,
            len(tools),
            self._tool_names,
        )

    async def invoke(self, message: str) -> AgentInvokeResult:
        mode = normalize_runtime_mode(self._runtime_mode or resolve_agent_runtime_mode())
        if mode == "http":
            if self._agent_runtime is None:
                raise RuntimeError(
                    "JOB_REQUEST_HELPER http mode requires agent_runtime "
                    f"(local_agent_id={STATIC_CONFIG.agent_id})"
                )
            return await self._agent_runtime.invoke(
                AgentInvokeRequest(
                    agent_id=STATIC_CONFIG.agent_id,
                    message=message,
                )
            )

        if self._agent is None:
            await self.initialize(mode)
        assert self._agent is not None
        return await invoke_agent(
            self._agent,
            message,
            self._mcp_manager,
            agent_id=STATIC_CONFIG.agent_id,
            agent_name=STATIC_CONFIG.agent_name,
            mcp_server_keys=list(MCP_SERVER_KEYS),
        )

    def status(self) -> dict[str, Any]:
        return {
            "agent_id": STATIC_CONFIG.agent_id,
            "agent_name": STATIC_CONFIG.agent_name,
            "ready": self.is_ready,
            "runtime_mode": self._runtime_mode,
            "mcp_server_keys": list(MCP_SERVER_KEYS),
            "tools": [{"name": name} for name in self._tool_names],
        }


job_request_helper_service = JobRequestHelperService()
