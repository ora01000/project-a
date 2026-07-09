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
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


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


def _estimate_tokens(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    return max(1, len(stripped) // 4)


def _usage_from_metadata(metadata: dict[str, Any]) -> tuple[int, int] | None:
    usage = metadata.get("token_usage") or metadata.get("usage")
    if not isinstance(usage, dict):
        return None

    input_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
    output_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
    if input_tokens is None and output_tokens is None:
        total_tokens = usage.get("total_tokens")
        if total_tokens is None:
            return None
        return int(total_tokens), 0

    return int(input_tokens or 0), int(output_tokens or 0)


def extract_token_usage_from_messages(messages: list[Any]) -> tuple[int, int]:
    input_tokens = 0
    output_tokens = 0
    metadata_found = False

    for message in messages:
        metadata = getattr(message, "response_metadata", None) or {}
        if isinstance(metadata, dict):
            usage = _usage_from_metadata(metadata)
            if usage is not None:
                metadata_found = True
                prompt_tokens, completion_tokens = usage
                input_tokens += prompt_tokens
                output_tokens += completion_tokens
                continue

        content = _extract_message_content(message)
        estimated = _estimate_tokens(content)
        if isinstance(message, HumanMessage):
            input_tokens += estimated
        elif isinstance(message, AIMessage):
            output_tokens += estimated

    if metadata_found:
        return input_tokens, output_tokens

    return input_tokens, output_tokens


def extract_token_usage_from_text(input_text: str, output_text: str) -> tuple[int, int]:
    return _estimate_tokens(input_text), _estimate_tokens(output_text)


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
    input_tokens, output_tokens = extract_token_usage_from_messages(messages)
    return AgentInvokeResult(
        content=content,
        tools_used=tools_used,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
