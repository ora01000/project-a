from dataclasses import dataclass
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.app.llm.factory import get_llm
from backend.app.mcp.client import MCPClientManager
from backend.app.mcp.sanitize import sanitize_tool_arguments, wrap_tool_with_argument_sanitizer
from langgraph.prebuilt import create_react_agent

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentDefinition:
    agent_id: str
    name: str
    role: str
    mcp_server_keys: list[str]
    system_prompt: str


@dataclass(frozen=True)
class ToolUsage:
    name: str
    mcp_server: str | None = None


@dataclass(frozen=True)
class AgentInvokeResult:
    content: str
    tools_used: list[ToolUsage]


def _aggregate_mcp_status(mcp_manager: MCPClientManager, server_keys: list[str]) -> str:
    statuses = [mcp_manager.connection_status.get(key, "unknown") for key in server_keys]
    if not server_keys:
        return "unknown"

    enabled_statuses = [status for status in statuses if status != "disabled"]
    if not enabled_statuses:
        return "disabled"
    if all(status == "connected" for status in enabled_statuses):
        return "connected"
    if any(status == "connected" for status in enabled_statuses):
        return "partial"
    return enabled_statuses[0]


def extract_tools_used(messages: list[Any], mcp_manager: MCPClientManager | None = None) -> list[ToolUsage]:
    seen: set[str] = set()
    tools_used: list[ToolUsage] = []

    for message in messages:
        if not isinstance(message, AIMessage) or not message.tool_calls:
            continue

        for tool_call in message.tool_calls:
            name = tool_call.get("name") if isinstance(tool_call, dict) else getattr(tool_call, "name", None)
            if not name or name in seen:
                continue
            seen.add(name)

            raw_args = tool_call.get("args") if isinstance(tool_call, dict) else getattr(tool_call, "args", {})
            if isinstance(raw_args, dict):
                sanitized_args = sanitize_tool_arguments(raw_args)
                if sanitized_args != raw_args:
                    logger.warning("Sanitized tool call args for %s: %s -> %s", name, raw_args, sanitized_args)

            mcp_server = mcp_manager.get_tool_server(name) if mcp_manager else None
            tools_used.append(ToolUsage(name=name, mcp_server=mcp_server))

    return tools_used


def _extract_message_content(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = [part.get("text", "") for part in content if isinstance(part, dict)]
        return "".join(text_parts) or str(content)
    return str(content)


async def build_agent(
    definition: AgentDefinition,
    mcp_manager: MCPClientManager,
) -> Any:
    llm = get_llm()
    tools = [
        wrap_tool_with_argument_sanitizer(tool)
        for tool in await mcp_manager.get_tools_for_servers(definition.mcp_server_keys)
    ]
    prompt = definition.system_prompt
    if not tools:
        server_keys = ", ".join(definition.mcp_server_keys)
        prompt = (
            f"{definition.system_prompt}\n\n"
            f"The MCP server(s) for this agent ({server_keys}) are not connected yet. "
            "Inform the user that MCP endpoints must be configured via environment variables "
            "(MCP_<SERVER>_URL, MCP_<SERVER>_ENABLED) or config/mcp_servers.yaml."
        )

    return create_react_agent(
        model=llm,
        tools=tools,
        prompt=SystemMessage(content=prompt),
    )


async def invoke_agent(
    agent: Any,
    message: str,
    mcp_manager: MCPClientManager | None = None,
) -> AgentInvokeResult:
    result = await agent.ainvoke({"messages": [HumanMessage(content=message)]})
    messages = result.get("messages", [])
    if not messages:
        return AgentInvokeResult(content="No response generated.", tools_used=[])

    tools_used = extract_tools_used(messages, mcp_manager)
    content = _extract_message_content(messages[-1])
    return AgentInvokeResult(content=content, tools_used=tools_used)
