import logging
from typing import Any

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from backend.app.config import MCPServerConfig

logger = logging.getLogger(__name__)


def _to_client_config(server_key: str, config: MCPServerConfig) -> dict[str, Any]:
    transport = config.transport
    if transport == "streamable_http":
        transport = "http"

    entry: dict[str, Any] = {
        "transport": transport,
        "url": config.url,
    }
    token = (config.auth_token or "").strip()
    if token:
        entry["headers"] = {"Authorization": f"Bearer {token}"}
    return {server_key: entry}


def _rename_tool(tool: BaseTool, name: str) -> BaseTool:
    if tool.name == name:
        return tool
    try:
        return tool.model_copy(update={"name": name})
    except Exception:
        cloned = tool.copy() if hasattr(tool, "copy") else tool
        cloned.name = name
        return cloned


def _prefixed_tool_name(server_key: str, tool_name: str) -> str:
    return f"{server_key}__{tool_name}"


class MCPClientManager:
    def __init__(self, servers: dict[str, MCPServerConfig]) -> None:
        self._servers = servers
        self._tools_by_server: dict[str, list[BaseTool]] = {}
        self._tool_server_map: dict[str, str] = {}
        self._connection_status: dict[str, str] = {}

    @property
    def connection_status(self) -> dict[str, str]:
        return dict(self._connection_status)

    async def _connect_server(self, server_key: str, config: MCPServerConfig) -> None:
        if not config.enabled:
            self._connection_status[server_key] = "disabled"
            self._tools_by_server[server_key] = []
            return

        try:
            client = MultiServerMCPClient(_to_client_config(server_key, config))
            tools = await client.get_tools()
            self._tool_server_map = {
                name: mapped_server
                for name, mapped_server in self._tool_server_map.items()
                if mapped_server != server_key
            }
            self._tools_by_server[server_key] = tools
            for tool in tools:
                self._tool_server_map[tool.name] = server_key
                self._tool_server_map[_prefixed_tool_name(server_key, tool.name)] = server_key
            self._connection_status[server_key] = "connected"
            logger.info("MCP server '%s' connected with %d tools", server_key, len(tools))
        except Exception as exc:
            self._tools_by_server[server_key] = []
            self._connection_status[server_key] = f"error: {exc}"
            logger.warning("MCP server '%s' connection failed: %s", server_key, exc)

    async def initialize(self) -> None:
        for server_key, config in self._servers.items():
            await self._connect_server(server_key, config)

    async def refresh_health(self) -> None:
        for server_key, config in self._servers.items():
            await self._connect_server(server_key, config)

    async def get_tools(self, server_key: str) -> list[BaseTool]:
        return self._tools_by_server.get(server_key, [])

    async def get_tools_for_servers(self, server_keys: list[str]) -> list[BaseTool]:
        collected: list[tuple[str, BaseTool]] = []
        for server_key in server_keys:
            for tool in await self.get_tools(server_key):
                collected.append((server_key, tool))

        # project-f MCP servers all expose the same tool name (`run_cli`).
        # Prefix with server key when the agent binds multiple such servers.
        raw_names = [tool.name for _, tool in collected]
        needs_prefix = len(raw_names) != len(set(raw_names))

        tools: list[BaseTool] = []
        seen_names: set[str] = set()
        for server_key, tool in collected:
            name = _prefixed_tool_name(server_key, tool.name) if needs_prefix else tool.name
            if name in seen_names:
                continue
            seen_names.add(name)
            tools.append(_rename_tool(tool, name) if name != tool.name else tool)
        return tools

    def get_tool_server(
        self,
        tool_name: str,
        *,
        server_keys: list[str] | None = None,
    ) -> str | None:
        if server_keys is not None:
            for server_key in server_keys:
                if tool_name.startswith(f"{server_key}__"):
                    return server_key
                for tool in self._tools_by_server.get(server_key, []):
                    if tool.name == tool_name:
                        return server_key
                    if _prefixed_tool_name(server_key, tool.name) == tool_name:
                        return server_key
            return None
        return self._tool_server_map.get(tool_name)
