"""
MCP Client Implementation

Real MCP client using the official MCP Python SDK.
Allows Aki agents to call tools from external MCP servers.
"""

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from pydantic import BaseModel, Field

# Check if MCP is available
try:
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client, StdioServerParameters
    from mcp.client.streamable_http import streamablehttp_client

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    ClientSession = None  # type: ignore


class MCPServerConfig(BaseModel):
    """Configuration for connecting to an MCP server."""

    name: str = Field(..., description="Server name for identification")
    command: str = Field(default="", description="Command to start the server (stdio transport)")
    args: list[str] = Field(default_factory=list, description="Command arguments")
    env: dict[str, str] = Field(
        default_factory=dict, description="Environment variables"
    )
    url: str | None = Field(default=None, description="HTTP URL for streamable HTTP transport")
    transport: str = Field(default="stdio", description="Transport type: 'stdio' or 'streamable-http'")


class MCPToolInfo(BaseModel):
    """Information about an MCP tool."""

    name: str
    description: str
    input_schema: dict[str, Any]


class MCPClient:
    """
    MCP Client for connecting to external MCP servers.

    Allows Aki to use tools from other MCP-compatible services.
    """

    def __init__(self):
        """Initialize the MCP client."""
        if not MCP_AVAILABLE:
            raise ImportError(
                "MCP SDK not installed. Install with: pip install mcp"
            )

        self._sessions: dict[str, ClientSession] = {}
        self._tools_cache: dict[str, list[MCPToolInfo]] = {}

    @asynccontextmanager
    async def connect(
        self, config: MCPServerConfig
    ) -> AsyncIterator["ClientSession"]:
        """
        Connect to an MCP server.

        Args:
            config: Server configuration

        Yields:
            MCP ClientSession
        """
        if config.transport == "streamable-http" and config.url:
            async with streamablehttp_client(config.url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._sessions[config.name] = session
                    try:
                        yield session
                    finally:
                        self._sessions.pop(config.name, None)
                        self._tools_cache.pop(config.name, None)
        else:
            server_params = StdioServerParameters(
                command=config.command,
                args=config.args,
                env=config.env if config.env else None,
            )
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._sessions[config.name] = session
                    try:
                        yield session
                    finally:
                        self._sessions.pop(config.name, None)
                        self._tools_cache.pop(config.name, None)

    async def list_tools(
        self, session: "ClientSession", server_name: str
    ) -> list[MCPToolInfo]:
        """
        List available tools from an MCP server.

        Args:
            session: Active MCP session
            server_name: Server name for caching

        Returns:
            List of available tools
        """
        # Check cache
        if server_name in self._tools_cache:
            return self._tools_cache[server_name]

        # Fetch tools
        result = await session.list_tools()

        tools = [
            MCPToolInfo(
                name=tool.name,
                description=tool.description or "",
                input_schema=tool.inputSchema,
            )
            for tool in result.tools
        ]

        # Cache
        self._tools_cache[server_name] = tools

        return tools

    async def call_tool(
        self,
        session: "ClientSession",
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """
        Call a tool on an MCP server.

        Args:
            session: Active MCP session
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool result
        """
        result = await session.call_tool(tool_name, arguments)

        # Extract content
        if result.content:
            # Return first text content
            for content in result.content:
                if hasattr(content, "text"):
                    return content.text
            return result.content

        return None


class MCPToolWrapper:
    """
    Wrapper to use MCP tools as Aki tools.

    Bridges external MCP tools into the Aki tool system.
    """

    def __init__(
        self,
        client: MCPClient,
        server_config: MCPServerConfig,
        tool_info: MCPToolInfo,
    ):
        """
        Initialize the wrapper.

        Args:
            client: MCP client instance
            server_config: Server configuration
            tool_info: Tool information
        """
        self.client = client
        self.server_config = server_config
        self.tool_info = tool_info

        # Tool interface compatibility
        self.name = f"{server_config.name}:{tool_info.name}"
        self.description = tool_info.description

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """
        Execute the MCP tool.

        Args:
            **kwargs: Tool arguments

        Returns:
            Tool result
        """
        async with self.client.connect(self.server_config) as session:
            result = await self.client.call_tool(
                session, self.tool_info.name, kwargs
            )
            return {"success": True, "data": result}

    def to_openai_schema(self) -> dict[str, Any]:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.tool_info.input_schema,
            },
        }


async def discover_mcp_tools(
    config: MCPServerConfig,
) -> list[MCPToolWrapper]:
    """
    Discover and wrap all tools from an MCP server.

    Args:
        config: Server configuration

    Returns:
        List of wrapped tools
    """
    client = MCPClient()
    wrappers = []

    async with client.connect(config) as session:
        tools = await client.list_tools(session, config.name)

        for tool in tools:
            wrapper = MCPToolWrapper(client, config, tool)
            wrappers.append(wrapper)

    return wrappers


# Convenience function to check if MCP is available
def is_mcp_available() -> bool:
    """Check if MCP SDK is installed."""
    return MCP_AVAILABLE
