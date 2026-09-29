"""HTTP API exposed by the Agent Runtime service."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from backend.app.agent_runtime.schemas import (
    ReloadAgentsBody,
    RuntimeHealthResponse,
    RuntimeInvokeBody,
    RuntimePlannedStepBody,
    result_to_payload,
)
from backend.app.disabled_features import is_removed_agent_id, raise_disabled_feature
from backend.app.services.agent_invocation import AgentInvocationError, invoke_agent_for_planned_step

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runtime", tags=["agent-runtime"])


def _runtime_manager(request: Request) -> Any:
    return request.app.state.runtime_manager


@router.get("/health")
async def runtime_health(request: Request) -> dict[str, Any]:
    manager = _runtime_manager(request)
    return {
        "status": "ok",
        "agents": list(manager.agents.keys()),
        "agent_status": manager.get_agent_health_status(),
        "mcp": manager.mcp_manager.connection_status if manager.mcp_manager else {},
    }


@router.get("/agents/{agent_id}/health", response_model=RuntimeHealthResponse)
async def agent_runtime_health(agent_id: str, request: Request) -> RuntimeHealthResponse:
    manager = _runtime_manager(request)
    status = manager.get_agent_health_status().get(agent_id, "unknown")
    return RuntimeHealthResponse(agent_id=agent_id, status=status)


@router.post("/agents/{agent_id}/invoke")
async def invoke_agent(agent_id: str, payload: RuntimeInvokeBody, request: Request) -> dict:
    from backend.app.services.agent_invocation import invoke_agent_by_id

    if is_removed_agent_id(agent_id):
        raise_disabled_feature()

    manager = _runtime_manager(request)

    if agent_id not in manager.agents:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    try:
        result = await invoke_agent_by_id(
            manager,
            agent_id,
            payload.message,
            caller_agent_id=payload.caller_agent_id,
            agent_runtime=getattr(request.app.state, "agent_runtime", None),
        )
    except AgentInvocationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return result_to_payload(result).model_dump()


@router.post("/agents/{agent_id}/invoke-planned-step")
async def invoke_planned_step(agent_id: str, payload: RuntimePlannedStepBody, request: Request) -> dict:
    raise_disabled_feature()


@router.post("/agents/reload")
async def reload_agents(payload: ReloadAgentsBody, request: Request) -> dict[str, int]:
    manager = _runtime_manager(request)
    await manager.reload_definitions(payload.definitions)
    return {"reloaded": len(payload.definitions)}


@router.get("/agents/{agent_id}/tools")
async def list_agent_tools(agent_id: str, request: Request) -> list[dict[str, str]]:
    manager = _runtime_manager(request)
    try:
        definition = manager.get_definition(agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found") from exc

    tools: list[dict[str, str]] = []
    if manager.mcp_manager and definition.mcp_server_keys:
        for tool in await manager.mcp_manager.get_tools_for_servers(definition.mcp_server_keys):
            tools.append(
                {
                    "name": tool.name,
                    "description": getattr(tool, "description", "") or "",
                }
            )

    return tools
