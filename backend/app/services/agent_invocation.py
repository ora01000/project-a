from typing import Any

from backend.app.agents.base import (
    AgentInvokeResult,
    build_planned_step_agent,
    invoke_agent,
)
from backend.app.agents.remote_agent import REMOTE_AGENT_MARKER
from backend.app.disabled_features import is_removed_agent_id


class AgentInvocationError(Exception):
    pass


async def invoke_agent_by_id(
    agent_manager: Any,
    agent_id: str,
    message: str,
    *,
    caller_agent_id: str | None = None,
    agent_runtime: Any | None = None,
) -> AgentInvokeResult:
    del caller_agent_id, agent_runtime

    if is_removed_agent_id(agent_id):
        raise AgentInvocationError(f"Agent '{agent_id}' is disabled")

    if agent_id not in agent_manager.agents:
        raise AgentInvocationError(f"Agent '{agent_id}' not found")

    agent = agent_manager.get_agent(agent_id)
    if agent is REMOTE_AGENT_MARKER:
        raise AgentInvocationError(
            f"Agent '{agent_id}' is configured for remote runtime execution"
        )

    try:
        definition = agent_manager.get_definition(agent_id)
        agent_name = definition.name
        mcp_server_keys = list(definition.mcp_server_keys)
    except KeyError:
        agent_name = agent_id
        mcp_server_keys = None
    return await invoke_agent(
        agent,
        message,
        agent_manager.mcp_manager,
        agent_id=agent_id,
        agent_name=agent_name,
        mcp_server_keys=mcp_server_keys,
    )


async def invoke_agent_for_planned_step(
    agent_manager: Any,
    agent_id: str,
    message: str,
    *,
    tool_name: str | None = None,
    tool_params: dict[str, Any] | None = None,
    caller_agent_id: str | None = None,
    agent_runtime: Any | None = None,
) -> AgentInvokeResult:
    del tool_params, caller_agent_id, agent_runtime

    if is_removed_agent_id(agent_id):
        raise AgentInvocationError(f"Agent '{agent_id}' is disabled")

    planned = (tool_name or "").strip()

    if agent_id not in agent_manager.agents:
        raise AgentInvocationError(f"Agent '{agent_id}' not found")

    agent = agent_manager.get_agent(agent_id)
    if agent is REMOTE_AGENT_MARKER:
        raise AgentInvocationError(
            f"Agent '{agent_id}' is configured for remote runtime execution"
        )

    try:
        definition = agent_manager.get_definition(agent_id)
    except KeyError as exc:
        raise AgentInvocationError(f"Agent '{agent_id}' not found") from exc

    try:
        step_agent = await build_planned_step_agent(
            definition,
            agent_manager.mcp_manager,
            tool_name=planned or None,
        )
    except ValueError as exc:
        raise AgentInvocationError(str(exc)) from exc

    return await invoke_agent(
        step_agent,
        message,
        agent_manager.mcp_manager,
        agent_id=agent_id,
        agent_name=definition.name,
        mcp_server_keys=list(definition.mcp_server_keys),
    )
