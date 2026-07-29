"""Agent runtime abstraction — Control Plane ↔ external sandbox boundary."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from backend.app.agent_runtime.schemas import (
    AgentInvokeResultPayload,
    ReloadAgentsBody,
    RuntimeInvokeBody,
    RuntimePlannedStepBody,
    definition_to_payload,
    payload_to_result,
)
from backend.app.agents.base import AgentDefinition, AgentInvokeResult, ToolUsage

logger = logging.getLogger(__name__)

SANDBOX_RUNTIME_MODES = frozenset({"mock", "http", "local"})


def normalize_runtime_mode(mode: str | None) -> str:
    """Normalize runtime mode. ``local`` is a legacy alias for ``mock``."""
    normalized = (mode or "mock").strip().lower()
    if normalized == "local":
        return "mock"
    return normalized


def is_sandbox_runtime_mode(mode: str | None) -> bool:
    return normalize_runtime_mode(mode) in SANDBOX_RUNTIME_MODES


@dataclass(frozen=True)
class AgentInvokeRequest:
    """Single chat-style invocation against an agent."""

    agent_id: str
    message: str
    caller_agent_id: str | None = None
    trace_id: str | None = None
    control_plane_base_url: str | None = None


@dataclass(frozen=True)
class AgentPlannedStepRequest:
    """Job execution step — constrained to one planned MCP tool."""

    agent_id: str
    message: str
    tool_name: str | None = None
    tool_params: dict[str, Any] | None = None
    caller_agent_id: str | None = None
    trace_id: str | None = None
    control_plane_base_url: str | None = None


class AgentRuntimeClient(Protocol):
    """Contract between Control Plane and external Agent Runtime sandbox."""

    async def invoke(self, request: AgentInvokeRequest) -> AgentInvokeResult:
        """Chat / helpdesk / inventory / system agent execution."""
        ...

    async def invoke_planned_step(self, request: AgentPlannedStepRequest) -> AgentInvokeResult:
        """Job execution step with optional single-tool binding."""
        ...

    async def reload_definitions(self, definitions: list[AgentDefinition]) -> None:
        """Apply agent definition changes on the sandbox runtime."""
        ...

    async def get_runtime_health(self, agent_id: str) -> str:
        """Per-agent runtime health: connected | partial | unavailable | mock | unknown."""
        ...

    async def get_runtime_summary(self) -> dict[str, Any]:
        """MCP connection map and per-agent health from the runtime."""
        ...

    async def list_agent_tools(self, agent_id: str) -> list[dict[str, str]]:
        """Tool catalog for planning and UI."""
        ...


class LocalAgentRuntimeClient:
    """In-process runtime used by the standalone agent-runtime service only."""

    def __init__(self, agent_manager: Any) -> None:
        self._agent_manager = agent_manager

    async def invoke(self, request: AgentInvokeRequest) -> AgentInvokeResult:
        from backend.app.services.agent_invocation import invoke_agent_by_id

        return await invoke_agent_by_id(
            self._agent_manager,
            request.agent_id,
            request.message,
            caller_agent_id=request.caller_agent_id,
            agent_runtime=self,
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
            agent_runtime=self,
        )

    async def reload_definitions(self, definitions: list[AgentDefinition]) -> None:
        del definitions

    async def get_runtime_health(self, agent_id: str) -> str:
        return self._agent_manager.get_agent_health_status().get(agent_id, "unknown")

    async def get_runtime_summary(self) -> dict[str, Any]:
        manager = self._agent_manager
        return {
            "mcp": manager.mcp_manager.connection_status if manager.mcp_manager else {},
            "agent_status": manager.get_agent_health_status(),
        }

    async def list_agent_tools(self, agent_id: str) -> list[dict[str, str]]:
        from backend.app.services.agent_tool_catalog import list_tools_for_definition

        definition = self._agent_manager.get_definition(agent_id)
        return await list_tools_for_definition(self._agent_manager, definition)


class MockAgentRuntimeClient:
    """Dev-only stub runtime — no LangGraph/MCP/sandbox required on the control plane."""

    def __init__(self, agent_manager: Any) -> None:
        self._agent_manager = agent_manager

    def _known_agent_ids(self) -> list[str]:
        return list(self._agent_manager.agents.keys())

    async def invoke(self, request: AgentInvokeRequest) -> AgentInvokeResult:
        content = (
            f"[mock runtime] agent={request.agent_id} received your message "
            f"({len(request.message)} chars).\n\n"
            "Set AGENT_RUNTIME_MODE=http and AGENT_RUNTIME_HTTP_BASE_URL to connect "
            "to an external sandbox runtime for real execution."
        )
        return AgentInvokeResult(content=content, tools_used=[], input_tokens=0, output_tokens=0)

    async def invoke_planned_step(self, request: AgentPlannedStepRequest) -> AgentInvokeResult:
        tool_name = request.tool_name or "agent_invoke"
        content = (
            f"[mock runtime] planned step on {request.agent_id} "
            f"(tool={tool_name}): {request.message[:500]}"
        )
        tools_used: list[ToolUsage] = []
        if tool_name != "agent_invoke":
            tools_used.append(ToolUsage(name=tool_name, mcp_server="mock"))
        return AgentInvokeResult(content=content, tools_used=tools_used)

    async def reload_definitions(self, definitions: list[AgentDefinition]) -> None:
        logger.info("Mock runtime: accepted %d agent definition(s) (no-op)", len(definitions))

    async def get_runtime_health(self, agent_id: str) -> str:
        return "mock" if agent_id in self._agent_manager.agents else "unknown"

    async def get_runtime_summary(self) -> dict[str, Any]:
        agent_status = {agent_id: "mock" for agent_id in self._known_agent_ids()}
        return {
            "mcp": {
                "kubernetes": "mock",
                "kubectl_ai": "mock",
                "kubevirt": "mock",
                "vcenter": "mock",
                "ansible": "disabled",
            },
            "agent_status": agent_status,
        }

    async def list_agent_tools(self, agent_id: str) -> list[dict[str, str]]:
        return [
            {"name": "mock_tool", "description": f"Mock MCP tool for {agent_id}"},
            {"name": "agent_invoke", "description": "Respond without MCP tools"},
        ]


class HttpAgentRuntimeClient:
    """Remote agent runtime over HTTP (external sandbox)."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 300.0,
        api_key: str = "",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._api_key = api_key.strip()

    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            return {}
        return {"X-Runtime-Api-Key": self._api_key}

    async def _request(self, method: str, path: str, *, json_body: dict | None = None) -> Any:
        url = f"{self._base_url}{path}"
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.request(method, url, json=json_body, headers=self._headers())
            response.raise_for_status()
            return response.json()

    async def _request_json(self, method: str, path: str, *, json_body: dict | None = None) -> dict:
        payload = await self._request(method, path, json_body=json_body)
        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected runtime response from {path}")
        return payload

    async def invoke(self, request: AgentInvokeRequest) -> AgentInvokeResult:
        payload = await self._request_json(
            "POST",
            f"/runtime/agents/{request.agent_id}/invoke",
            json_body=RuntimeInvokeBody(
                message=request.message,
                caller_agent_id=request.caller_agent_id,
                trace_id=request.trace_id,
                control_plane_base_url=request.control_plane_base_url,
            ).model_dump(),
        )
        return payload_to_result(AgentInvokeResultPayload.model_validate(payload))

    async def invoke_planned_step(self, request: AgentPlannedStepRequest) -> AgentInvokeResult:
        payload = await self._request_json(
            "POST",
            f"/runtime/agents/{request.agent_id}/invoke-planned-step",
            json_body=RuntimePlannedStepBody(
                message=request.message,
                tool_name=request.tool_name,
                tool_params=request.tool_params,
                caller_agent_id=request.caller_agent_id,
                trace_id=request.trace_id,
                control_plane_base_url=request.control_plane_base_url,
            ).model_dump(),
        )
        return payload_to_result(AgentInvokeResultPayload.model_validate(payload))

    async def reload_definitions(self, definitions: list[AgentDefinition]) -> None:
        await self._request_json(
            "POST",
            "/runtime/agents/reload",
            json_body=ReloadAgentsBody(
                definitions=[definition_to_payload(defn) for defn in definitions],
            ).model_dump(),
        )

    async def get_runtime_health(self, agent_id: str) -> str:
        payload = await self._request_json("GET", f"/runtime/agents/{agent_id}/health")
        return str(payload.get("status", "unknown"))

    async def get_runtime_summary(self) -> dict[str, Any]:
        payload = await self._request_json("GET", "/runtime/health")
        return {
            "mcp": payload.get("mcp", {}) if isinstance(payload.get("mcp"), dict) else {},
            "agent_status": payload.get("agent_status", {})
            if isinstance(payload.get("agent_status"), dict)
            else {},
        }

    async def list_agent_tools(self, agent_id: str) -> list[dict[str, str]]:
        payload = await self._request("GET", f"/runtime/agents/{agent_id}/tools")
        if not isinstance(payload, list):
            raise RuntimeError(f"Unexpected tools response for agent '{agent_id}'")
        tools: list[dict[str, str]] = []
        for item in payload:
            if isinstance(item, dict) and item.get("name"):
                tools.append(
                    {
                        "name": str(item["name"]),
                        "description": str(item.get("description") or ""),
                    }
                )
        return tools


def create_agent_runtime_client(
    mode: str,
    *,
    agent_manager: Any | None = None,
    http_base_url: str | None = None,
    http_api_key: str = "",
    http_timeout_seconds: float = 300.0,
) -> AgentRuntimeClient:
    """Factory — ``AGENT_RUNTIME_MODE=mock|http`` (``local`` aliases ``mock``)."""
    normalized = normalize_runtime_mode(mode)
    if normalized == "mock":
        if agent_manager is None:
            raise ValueError("agent_manager is required for mock runtime mode")
        return MockAgentRuntimeClient(agent_manager)
    if normalized == "http":
        if not http_base_url:
            raise ValueError("http_base_url is required for http runtime mode")
        return HttpAgentRuntimeClient(
            http_base_url,
            timeout_seconds=http_timeout_seconds,
            api_key=http_api_key,
        )
    raise ValueError(f"Unsupported AGENT_RUNTIME_MODE: {mode!r} (use mock or http)")
