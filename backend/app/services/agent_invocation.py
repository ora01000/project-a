from typing import Any

from backend.app.agents.base import AgentInvokeResult, extract_token_usage_from_text, invoke_agent
from backend.app.agents.inventory_tool import INVENTORY_AGENT_ID
from backend.app.agents.inventory_agent import INVENTORY_AGENT_MARKER
from backend.app.agents.system_agents import SYSTEM_AGENT_MARKER, is_dashboard_system_agent_id


class AgentInvocationError(Exception):
    pass


async def invoke_agent_by_id(
    agent_manager: Any,
    agent_id: str,
    message: str,
    *,
    caller_agent_id: str | None = None,
) -> AgentInvokeResult:
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

    return await invoke_agent(agent, message, agent_manager.mcp_manager)
