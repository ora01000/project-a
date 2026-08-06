"""Agent runtime abstraction — Control Plane ↔ external sandbox boundary."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
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

logger = logging.getLogger(__name__)

SANDBOX_RUNTIME_MODES = frozenset({"mock", "http", "local"})

MOCK_RUNTIME_UNAVAILABLE_DETAIL = (
    "Mock runtime은 질의/응답(invoke)만 제공합니다. "
    "작업 실행·도구 조회 등은 AGENT_RUNTIME_MODE=http 로 샌드박스 런타임을 연결하세요."
)


@dataclass(frozen=True)
class RuntimeCapabilities:
    """Runtime APIs exposed to the control plane for the active mode."""

    invoke: bool = True
    planned_step: bool = True
    health_summary: bool = True
    agent_tools: bool = True
    reload_definitions: bool = True
    job_submission: bool = True

    def as_dict(self) -> dict[str, bool]:
        return {
            "invoke": self.invoke,
            "planned_step": self.planned_step,
            "health_summary": self.health_summary,
            "agent_tools": self.agent_tools,
            "reload_definitions": self.reload_definitions,
            "job_submission": self.job_submission,
        }


MOCK_RUNTIME_CAPABILITIES = RuntimeCapabilities(
    invoke=True,
    planned_step=False,
    health_summary=False,
    agent_tools=False,
    reload_definitions=False,
    job_submission=False,
)

FULL_RUNTIME_CAPABILITIES = RuntimeCapabilities()


class RuntimeCapabilityError(RuntimeError):
    """Raised when a control-plane caller hits an API the mock runtime does not expose."""


def get_runtime_capabilities(mode: str | None) -> RuntimeCapabilities:
    if normalize_runtime_mode(mode) == "mock":
        return MOCK_RUNTIME_CAPABILITIES
    return FULL_RUNTIME_CAPABILITIES


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
    session_id: str | None = None
    trace_id: str | None = None
    control_plane_base_url: str | None = None
    agentruntime_idx: int | None = None


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
        """Chat / helpdesk / system agent execution."""
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


def _record_invoke_failure(agent_manager: Any | None, agent_id: str, exc: Exception) -> None:
    if agent_manager is None:
        return
    mark_failure = getattr(agent_manager, "mark_agent_invoke_failure", None)
    if callable(mark_failure):
        mark_failure(agent_id, str(exc))


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
    """Dev runtime: invoke via AXIT mock HTTP APIs; other sandbox APIs disabled."""

    def __init__(
        self,
        agent_manager: Any,
        database_path: str | Path,
        *,
        axit_timeout_seconds: float = 3600.0,
    ) -> None:
        self._agent_manager = agent_manager
        self._database_path = database_path
        self._local = LocalAgentRuntimeClient(agent_manager)
        from backend.app.services.axit_platform_client import AxitPlatformClient

        self._axit_client = AxitPlatformClient(timeout_seconds=axit_timeout_seconds)

    async def invoke(self, request: AgentInvokeRequest) -> AgentInvokeResult:
        from backend.app.agents.base import ToolUsage
        from backend.app.db.agentruntime import build_axit_agent_id, get_agentruntime_by_agent_id
        from backend.app.services.axit_platform_client import AxitPlatformInvokeRequest

        axit_agent_id = build_axit_agent_id(request.agent_id)
        runtime_record = get_agentruntime_by_agent_id(
            self._database_path,
            axit_agent_id,
            runtime_mode="mock",
        )
        if runtime_record is None:
            return await self._local.invoke(request)

        try:
            axit_result = await self._axit_client.invoke(
                self._database_path,
                AxitPlatformInvokeRequest(
                    axit_agent_id=axit_agent_id,
                    message=request.message,
                    session_id=request.session_id,
                    enable_trace=True,
                ),
                runtime_record=runtime_record,
            )
        except Exception as exc:
            _record_invoke_failure(self._agent_manager, request.agent_id, exc)
            raise

        tools_used: list[ToolUsage] = []
        trace_payload = axit_result.trace
        if isinstance(trace_payload, dict):
            trace_tools = trace_payload.get("tools")
            if isinstance(trace_tools, list):
                for item in trace_tools:
                    if isinstance(item, dict) and item.get("name"):
                        tools_used.append(
                            ToolUsage(
                                name=str(item["name"]),
                                mcp_server=str(item["mcp_server"]) if item.get("mcp_server") else None,
                            ),
                        )
        elif isinstance(trace_payload, list):
            for entry in trace_payload:
                if not isinstance(entry, dict):
                    continue
                nested_tools = entry.get("tools")
                if not isinstance(nested_tools, list):
                    continue
                for item in nested_tools:
                    if isinstance(item, dict) and item.get("name"):
                        tools_used.append(
                            ToolUsage(
                                name=str(item["name"]),
                                mcp_server=str(item["mcp_server"]) if item.get("mcp_server") else None,
                            ),
                        )

        return AgentInvokeResult(content=axit_result.completion, tools_used=tools_used)

    async def invoke_planned_step(self, request: AgentPlannedStepRequest) -> AgentInvokeResult:
        raise RuntimeCapabilityError(MOCK_RUNTIME_UNAVAILABLE_DETAIL)

    async def reload_definitions(self, definitions: list[AgentDefinition]) -> None:
        raise RuntimeCapabilityError(MOCK_RUNTIME_UNAVAILABLE_DETAIL)

    async def get_runtime_health(self, agent_id: str) -> str:
        raise RuntimeCapabilityError(MOCK_RUNTIME_UNAVAILABLE_DETAIL)

    async def get_runtime_summary(self) -> dict[str, Any]:
        raise RuntimeCapabilityError(MOCK_RUNTIME_UNAVAILABLE_DETAIL)

    async def list_agent_tools(self, agent_id: str) -> list[dict[str, str]]:
        raise RuntimeCapabilityError(MOCK_RUNTIME_UNAVAILABLE_DETAIL)


class ExternalAxitRuntimeClient:
    """Server runtime: delegate all agent execution to external AXIT platform APIs."""

    def __init__(
        self,
        agent_manager: Any,
        database_path: str | Path,
        *,
        axit_timeout_seconds: float = 3600.0,
    ) -> None:
        self._agent_manager = agent_manager
        self._database_path = database_path
        from backend.app.services.axit_platform_client import AxitPlatformClient

        self._axit_client = AxitPlatformClient(timeout_seconds=axit_timeout_seconds)

    def _connected_agent_status(self) -> dict[str, str]:
        from backend.app.db.agentruntime import catalog_agent_id, list_agentruntime_records

        records = list_agentruntime_records(self._database_path, runtime_mode="http")
        statuses: dict[str, str] = {}
        for record in records:
            agent_id = catalog_agent_id(record)
            statuses[agent_id] = self._agent_manager.get_axit_agent_connection_status(agent_id)
        return statuses

    async def invoke(self, request: AgentInvokeRequest) -> AgentInvokeResult:
        from backend.app.agents.base import ToolUsage
        from backend.app.db.agentruntime import resolve_agentruntime_for_invoke
        from backend.app.services.axit_platform_client import AxitPlatformInvokeRequest

        runtime_record = resolve_agentruntime_for_invoke(
            self._database_path,
            catalog_agent_id=request.agent_id,
            agentruntime_idx=request.agentruntime_idx,
            runtime_mode="http",
        )
        if runtime_record is None:
            raise RuntimeError(f"No agentruntime record found for agent_id={request.agent_id!r}")

        try:
            axit_result = await self._axit_client.invoke(
                self._database_path,
                AxitPlatformInvokeRequest(
                    axit_agent_id=runtime_record.agent_id,
                    message=request.message,
                    session_id=request.session_id,
                    enable_trace=True,
                ),
                runtime_record=runtime_record,
            )
        except Exception as exc:
            _record_invoke_failure(self._agent_manager, request.agent_id, exc)
            raise

        tools_used: list[ToolUsage] = []
        trace_payload = axit_result.trace
        if isinstance(trace_payload, dict):
            trace_tools = trace_payload.get("tools")
            if isinstance(trace_tools, list):
                for item in trace_tools:
                    if isinstance(item, dict) and item.get("name"):
                        tools_used.append(
                            ToolUsage(
                                name=str(item["name"]),
                                mcp_server=str(item["mcp_server"]) if item.get("mcp_server") else None,
                            ),
                        )
        elif isinstance(trace_payload, list):
            for entry in trace_payload:
                if not isinstance(entry, dict):
                    continue
                nested_tools = entry.get("tools")
                if not isinstance(nested_tools, list):
                    continue
                for item in nested_tools:
                    if isinstance(item, dict) and item.get("name"):
                        tools_used.append(
                            ToolUsage(
                                name=str(item["name"]),
                                mcp_server=str(item["mcp_server"]) if item.get("mcp_server") else None,
                            ),
                        )

        return AgentInvokeResult(content=axit_result.completion, tools_used=tools_used)

    async def invoke_planned_step(self, request: AgentPlannedStepRequest) -> AgentInvokeResult:
        raise RuntimeCapabilityError(MOCK_RUNTIME_UNAVAILABLE_DETAIL)

    async def reload_definitions(self, definitions: list[AgentDefinition]) -> None:
        del definitions

    async def get_runtime_health(self, agent_id: str) -> str:
        return self._agent_manager.get_axit_agent_connection_status(agent_id)

    async def get_runtime_summary(self) -> dict[str, Any]:
        return {
            "mcp": {},
            "agent_status": self._connected_agent_status(),
        }

    async def list_agent_tools(self, agent_id: str) -> list[dict[str, str]]:
        return []


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
    database_path: str | Path | None = None,
    http_base_url: str | None = None,
    http_api_key: str = "",
    http_timeout_seconds: float = 3600.0,
) -> AgentRuntimeClient:
    """Factory — ``AGENT_RUNTIME_MODE=mock|http`` (``local`` aliases ``mock``)."""
    normalized = normalize_runtime_mode(mode)
    if normalized == "mock":
        if agent_manager is None:
            raise ValueError("agent_manager is required for mock runtime mode")
        if database_path is None:
            raise ValueError("database_path is required for mock runtime mode")
        return MockAgentRuntimeClient(
            agent_manager,
            database_path,
            axit_timeout_seconds=http_timeout_seconds,
        )
    if normalized == "http":
        if agent_manager is None:
            raise ValueError("agent_manager is required for http runtime mode")
        if database_path is None:
            raise ValueError("database_path is required for http runtime mode")
        return ExternalAxitRuntimeClient(
            agent_manager,
            database_path,
            axit_timeout_seconds=http_timeout_seconds,
        )
    raise ValueError(f"Unsupported AGENT_RUNTIME_MODE: {mode!r} (use mock or http)")
