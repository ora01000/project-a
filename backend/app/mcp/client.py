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

    return {
        server_key: {
            "transport": transport,
            "url": config.url,
        }
    }


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
        tools: list[BaseTool] = []
        seen_names: set[str] = set()
        for server_key in server_keys:
            for tool in await self.get_tools(server_key):
                if tool.name in seen_names:
                    continue
                seen_names.add(tool.name)
                tools.append(tool)
        return tools

    def get_tool_server(self, tool_name: str) -> str | None:
        return self._tool_server_map.get(tool_name)
