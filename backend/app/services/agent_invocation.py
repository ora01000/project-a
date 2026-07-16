from typing import Any

from backend.app.agents.base import (
    AgentInvokeResult,
    build_planned_step_agent,
    extract_token_usage_from_text,
    invoke_agent,
)
from backend.app.agents.inventory_tool import INVENTORY_AGENT_ID, QUERY_INVENTORY_TOOL_NAME
from backend.app.agents.inventory_agent import INVENTORY_AGENT_MARKER
from backend.app.agents.system_agents import (
    HELPDESK_AGENT_ID,
    SYSTEM_AGENT_MARKER,
    is_dashboard_system_agent_id,
)


class AgentInvocationError(Exception):
    pass


async def invoke_agent_by_id(
    agent_manager: Any,
    agent_id: str,
    message: str,
    *,
    caller_agent_id: str | None = None,
) -> AgentInvokeResult:
    if agent_id == HELPDESK_AGENT_ID:
        from backend.app.services.helpdesk import handle_helpdesk_query

        return await handle_helpdesk_query(agent_manager, message)

    if agent_id == INVENTORY_AGENT_ID:
        inventory_service = getattr(agent_manager, "inventory_service", None)
        if inventory_service is None:
            raise AgentInvocationError("Inventory service is not initialized")

        result = await inventory_service.query(message)
        if caller_agent_id and caller_agent_id != INVENTORY_AGENT_ID:
            from backend.app.logging.agent_logger import log_agent_interaction

            log_agent_interaction(
                agent_id=INVENTORY_AGENT_ID,
                input_message=f"[caller={caller_agent_id}] {message}",
                output_message=result.content,
                tools_used=[],
            )
        return result

    if agent_id not in agent_manager.agents:
        raise AgentInvocationError(f"Agent '{agent_id}' not found")

    agent = agent_manager.get_agent(agent_id)
    if agent is INVENTORY_AGENT_MARKER:
        inventory_service = getattr(agent_manager, "inventory_service", None)
        if inventory_service is None:
            raise AgentInvocationError("Inventory service is not initialized")
        return await inventory_service.query(message)

    if agent is SYSTEM_AGENT_MARKER or is_dashboard_system_agent_id(agent_id):
        definition = agent_manager.get_definition(agent_id)
        content = (
            f"[{definition.name}]은(는) 통합 채팅에서 직접 질의하는 에이전트가 아닙니다. "
            f"역할: {definition.role}"
        )
        input_tokens, output_tokens = extract_token_usage_from_text(message, content)
        return AgentInvokeResult(
            content=content,
            tools_used=[],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    try:
        definition = agent_manager.get_definition(agent_id)
        agent_name = definition.name
    except KeyError:
        agent_name = agent_id
    return await invoke_agent(
        agent,
        message,
        agent_manager.mcp_manager,
        agent_id=agent_id,
        agent_name=agent_name,
    )


async def invoke_agent_for_planned_step(
    agent_manager: Any,
    agent_id: str,
    message: str,
    *,
    tool_name: str | None = None,
    tool_params: dict[str, Any] | None = None,
    caller_agent_id: str | None = None,
) -> AgentInvokeResult:
    """Invoke a regular agent constrained to the single tool from the job plan.

    The Job Execution system agent must not call tools itself; it only dispatches
    to the planned agent with the planned tool binding.
    """
    del tool_params  # params are already encoded into `message` by the caller

    planned = (tool_name or "").strip()

    if agent_id == INVENTORY_AGENT_ID or (
        agent_id in agent_manager.agents
        and agent_manager.get_agent(agent_id) is INVENTORY_AGENT_MARKER
    ):
        if planned and planned not in ("", "agent_invoke", QUERY_INVENTORY_TOOL_NAME):
            raise AgentInvocationError(
                f"Inventory agent cannot execute planned tool '{planned}'"
            )
        return await invoke_agent_by_id(
            agent_manager,
            INVENTORY_AGENT_ID,
            message,
            caller_agent_id=caller_agent_id,
        )

    if agent_id not in agent_manager.agents:
        raise AgentInvocationError(f"Agent '{agent_id}' not found")

    agent = agent_manager.get_agent(agent_id)
    if agent is SYSTEM_AGENT_MARKER or is_dashboard_system_agent_id(agent_id):
        raise AgentInvocationError(
            f"System agent '{agent_id}' cannot be invoked as a planned job step"
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
    )
