"""Agent runtime abstraction — Control Plane ↔ Agent Runtime boundary."""

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
from backend.app.agents.base import AgentDefinition, AgentInvokeResult
from backend.app.agents.inventory_tool import INVENTORY_AGENT_ID
from backend.app.agents.system_agents import HELPDESK_AGENT_ID, is_dashboard_system_agent_id

logger = logging.getLogger(__name__)


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

    async def get_runtime_summary(self) -> dict[str, Any]:
        """MCP connection map and per-agent health from the runtime."""
        ...

    async def list_agent_tools(self, agent_id: str) -> list[dict[str, str]]:
        """Tool catalog for planning and UI."""
        ...


def is_control_plane_local_agent(agent_id: str) -> bool:
    if agent_id in {HELPDESK_AGENT_ID, INVENTORY_AGENT_ID}:
        return True
    if is_dashboard_system_agent_id(agent_id):
        return True
    return False


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


class HttpAgentRuntimeClient:
    """Phase 2 — remote agent runtime over HTTP."""

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


class CompositeAgentRuntimeClient:
    """Routes system/helpdesk/inventory locally and regular agents to HTTP runtime."""

    def __init__(self, local: LocalAgentRuntimeClient, remote: HttpAgentRuntimeClient) -> None:
        self._local = local
        self._remote = remote

    def _pick(self, agent_id: str) -> AgentRuntimeClient:
        if is_control_plane_local_agent(agent_id):
            return self._local
        return self._remote

    async def invoke(self, request: AgentInvokeRequest) -> AgentInvokeResult:
        return await self._pick(request.agent_id).invoke(request)

    async def invoke_planned_step(self, request: AgentPlannedStepRequest) -> AgentInvokeResult:
        return await self._pick(request.agent_id).invoke_planned_step(request)

    async def reload_definitions(self, definitions: list[AgentDefinition]) -> None:
        await self._remote.reload_definitions(definitions)

    async def get_runtime_health(self, agent_id: str) -> str:
        if is_control_plane_local_agent(agent_id):
            return await self._local.get_runtime_health(agent_id)
        return await self._remote.get_runtime_health(agent_id)

    async def get_runtime_summary(self) -> dict[str, Any]:
        local_summary = await self._local.get_runtime_summary()
        try:
            remote_summary = await self._remote.get_runtime_summary()
        except Exception:
            logger.exception("Failed to fetch remote runtime health summary")
            remote_summary = {"mcp": {}, "agent_status": {}}

        agent_status = dict(remote_summary.get("agent_status", {}))
        for agent_id, status in local_summary.get("agent_status", {}).items():
            if is_control_plane_local_agent(agent_id):
                agent_status[agent_id] = status

        return {
            "mcp": remote_summary.get("mcp", {}),
            "agent_status": agent_status,
        }

    async def list_agent_tools(self, agent_id: str) -> list[dict[str, str]]:
        if is_control_plane_local_agent(agent_id):
            return await self._local.list_agent_tools(agent_id)
        return await self._remote.list_agent_tools(agent_id)


def create_agent_runtime_client(
    mode: str,
    *,
    agent_manager: Any | None = None,
    http_base_url: str | None = None,
    http_api_key: str = "",
    http_timeout_seconds: float = 300.0,
) -> AgentRuntimeClient:
    """Factory — ``AGENT_RUNTIME_MODE=local|http``."""
    normalized = (mode or "local").strip().lower()
    if normalized == "local":
        if agent_manager is None:
            raise ValueError("agent_manager is required for local runtime mode")
        return LocalAgentRuntimeClient(agent_manager)
    if normalized == "http":
        if agent_manager is None:
            raise ValueError("agent_manager is required for http runtime mode")
        if not http_base_url:
            raise ValueError("http_base_url is required for http runtime mode")
        local = LocalAgentRuntimeClient(agent_manager)
        remote = HttpAgentRuntimeClient(
            http_base_url,
            timeout_seconds=http_timeout_seconds,
            api_key=http_api_key,
        )
        return CompositeAgentRuntimeClient(local, remote)
    raise ValueError(f"Unsupported AGENT_RUNTIME_MODE: {mode!r}")
