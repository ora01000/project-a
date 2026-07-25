"""Agent runtime abstraction — Phase 1 draft.

Control Plane (FastAPI) delegates agent execution to an ``AgentRuntimeClient``.
Phase 1: ``LocalAgentRuntimeClient`` wraps existing ``agent_invocation`` helpers.
Phase 2: ``HttpAgentRuntimeClient`` talks to a remote agent runtime service.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from backend.app.agents.base import AgentDefinition, AgentInvokeResult


@dataclass(frozen=True)
class AgentInvokeRequest:
    """Single chat-style invocation against an agent."""

    agent_id: str
    message: str
    caller_agent_id: str | None = None
    trace_id: str | None = None


@dataclass(frozen=True)
class AgentPlannedStepRequest:
    """Job execution step — constrained to one planned MCP tool."""

    agent_id: str
    message: str
    tool_name: str | None = None
    tool_params: dict[str, Any] | None = None
    caller_agent_id: str | None = None
    trace_id: str | None = None


class AgentRuntimeClient(Protocol):
    """Contract between Control Plane and Agent Runtime."""

    async def invoke(self, request: AgentInvokeRequest) -> AgentInvokeResult:
        """Chat / helpdesk-delegated / inventory query."""
        ...

    async def invoke_planned_step(self, request: AgentPlannedStepRequest) -> AgentInvokeResult:
        """Job execution step with optional single-tool binding."""
        ...

    async def reload_definitions(self, definitions: list[AgentDefinition]) -> None:
        """Apply agent definition changes (local rebuild or remote push)."""
        ...

    async def get_runtime_health(self, agent_id: str) -> str:
        """Per-agent runtime health: connected | partial | unavailable | unknown."""
        ...


class LocalAgentRuntimeClient:
    """Phase 1 — delegates to in-process ``agent_invocation``."""

    def __init__(self, agent_manager: Any) -> None:
        self._agent_manager = agent_manager

    async def invoke(self, request: AgentInvokeRequest) -> AgentInvokeResult:
        from backend.app.services.agent_invocation import invoke_agent_by_id

        return await invoke_agent_by_id(
            self._agent_manager,
            request.agent_id,
            request.message,
            caller_agent_id=request.caller_agent_id,
        )

    async def invoke_planned_step(self, request: AgentPlannedStepRequest) -> AgentInvokeResult:
        from backend.app.services.agent_invocation import invoke_agent_for_planned_step

        return await invoke_agent_for_planned_step(
            self._agent_manager,
            request.agent_id,
            request.message,
            tool_name=request.tool_name,
            tool_params=request.tool_params,
            caller_agent_id=request.caller_agent_id,
        )

    async def reload_definitions(self, definitions: list[AgentDefinition]) -> None:
        del definitions  # Local path uses AgentManager.reload_agents(database_path) instead.
        raise NotImplementedError(
            "LocalAgentRuntimeClient.reload_definitions is not wired yet; "
            "call AgentManager.reload_agents(database_path) from Control Plane."
        )

    async def get_runtime_health(self, agent_id: str) -> str:
        return self._agent_manager.get_agent_health_status().get(agent_id, "unknown")


class HttpAgentRuntimeClient:
    """Phase 2 stub — remote agent runtime over HTTP."""

    def __init__(self, base_url: str, *, timeout_seconds: float = 120.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    async def invoke(self, request: AgentInvokeRequest) -> AgentInvokeResult:
        raise NotImplementedError("HttpAgentRuntimeClient.invoke — Phase 2")

    async def invoke_planned_step(self, request: AgentPlannedStepRequest) -> AgentInvokeResult:
        raise NotImplementedError("HttpAgentRuntimeClient.invoke_planned_step — Phase 2")

    async def reload_definitions(self, definitions: list[AgentDefinition]) -> None:
        raise NotImplementedError("HttpAgentRuntimeClient.reload_definitions — Phase 2")

    async def get_runtime_health(self, agent_id: str) -> str:
        raise NotImplementedError("HttpAgentRuntimeClient.get_runtime_health — Phase 2")


def create_agent_runtime_client(
    mode: str,
    *,
    agent_manager: Any | None = None,
    http_base_url: str | None = None,
) -> AgentRuntimeClient:
    """Factory — ``AGENT_RUNTIME_MODE=local|http``."""
    normalized = (mode or "local").strip().lower()
    if normalized == "local":
        if agent_manager is None:
            raise ValueError("agent_manager is required for local runtime mode")
        return LocalAgentRuntimeClient(agent_manager)
    if normalized == "http":
        if not http_base_url:
            raise ValueError("http_base_url is required for http runtime mode")
        return HttpAgentRuntimeClient(http_base_url)
    raise ValueError(f"Unsupported AGENT_RUNTIME_MODE: {mode!r}")
