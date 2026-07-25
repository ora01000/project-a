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
from backend.app.agents.inventory_tool import INVENTORY_AGENT_ID
from backend.app.agents.system_agents import HELPDESK_AGENT_ID, is_dashboard_system_agent_id
from backend.app.services.agent_invocation import AgentInvocationError, invoke_agent_for_planned_step
from backend.app.services.inventory_approval import remote_inventory_approval_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runtime", tags=["agent-runtime"])


def _runtime_manager(request: Request) -> Any:
    return request.app.state.runtime_manager


def _assert_runtime_executable(agent_id: str) -> None:
    if agent_id == HELPDESK_AGENT_ID or is_dashboard_system_agent_id(agent_id):
        raise HTTPException(
            status_code=400,
            detail=f"Agent '{agent_id}' must be executed on the control plane",
        )


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

    _assert_runtime_executable(agent_id)
    manager = _runtime_manager(request)

    if agent_id not in manager.agents:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    approval_ctx = None
    if payload.control_plane_base_url and payload.trace_id:
        approval_ctx = (payload.control_plane_base_url.rstrip("/"), payload.trace_id)

    try:
        async with remote_inventory_approval_context(approval_ctx):
            result = await invoke_agent_by_id(
                manager,
                agent_id,
                payload.message,
                caller_agent_id=payload.caller_agent_id,
            )
    except AgentInvocationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return result_to_payload(result).model_dump()


@router.post("/agents/{agent_id}/invoke-planned-step")
async def invoke_planned_step(agent_id: str, payload: RuntimePlannedStepBody, request: Request) -> dict:
    _assert_runtime_executable(agent_id)
    manager = _runtime_manager(request)

    if agent_id not in manager.agents:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    approval_ctx = None
    if payload.control_plane_base_url and payload.trace_id:
        approval_ctx = (payload.control_plane_base_url.rstrip("/"), payload.trace_id)

    try:
        async with remote_inventory_approval_context(approval_ctx):
            result = await invoke_agent_for_planned_step(
                manager,
                agent_id,
                payload.message,
                tool_name=payload.tool_name,
                tool_params=payload.tool_params,
                caller_agent_id=payload.caller_agent_id,
            )
    except AgentInvocationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return result_to_payload(result).model_dump()


@router.post("/agents/reload")
async def reload_agents(payload: ReloadAgentsBody, request: Request) -> dict[str, int]:
    manager = _runtime_manager(request)
    await manager.reload_definitions(payload.definitions)
    return {"reloaded": len(payload.definitions)}


@router.get("/agents/{agent_id}/tools")
async def list_agent_tools(agent_id: str, request: Request) -> list[dict[str, str]]:
    from backend.app.agents.inventory_tool import QUERY_INVENTORY_TOOL_NAME

    manager = _runtime_manager(request)
    try:
        definition = manager.get_definition(agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found") from exc

    tools: list[dict[str, str]] = []
    if agent_id == INVENTORY_AGENT_ID:
        tools.append(
            {
                "name": QUERY_INVENTORY_TOOL_NAME,
                "description": "Query the inventory database",
            }
        )

    if manager.mcp_manager and definition.mcp_server_keys:
        for tool in await manager.mcp_manager.get_tools_for_servers(definition.mcp_server_keys):
            tools.append(
                {
                    "name": tool.name,
                    "description": getattr(tool, "description", "") or "",
                }
            )

    return tools
