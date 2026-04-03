"""
MCP-to-BaseTool Adapter

Bridges MCP tools into Aki's BaseTool system so that agents
can call remote MCP server tools through the standard ReAct loop.
"""

from __future__ import annotations

from typing import Any

from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.mcp.client.client import MCPClient, MCPServerConfig, MCPToolInfo


# JSON Schema type → ToolParameter type mapping
_JSON_TYPE_MAP: dict[str, str] = {
    "string": "string",
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
    "array": "array",
    "object": "object",
}


def _schema_to_parameters(input_schema: dict[str, Any]) -> list[ToolParameter]:
    """Convert a JSON Schema ``properties`` dict to a list of ToolParameter."""
    properties = input_schema.get("properties") or {}
    required_set = set(input_schema.get("required") or [])
    params: list[ToolParameter] = []
    for prop_name, prop_def in properties.items():
        if not isinstance(prop_def, dict):
            continue
        params.append(
            ToolParameter(
                name=prop_name,
                type=_JSON_TYPE_MAP.get(prop_def.get("type", "string"), "string"),
                description=prop_def.get("description", ""),
                required=prop_name in required_set,
                default=prop_def.get("default"),
                enum=prop_def.get("enum"),
            )
        )
    return params


class MCPBaseTool(BaseTool):
    """A BaseTool that delegates execution to a remote MCP server tool.

    Each ``execute()`` call opens a fresh connection to the MCP server,
    calls the tool, and returns a ``ToolResult``.
    """

    # These are set per-instance in __init__; class-level defaults
    # satisfy the BaseTool contract so the ABC is happy.
    name: str = "__mcp_placeholder__"
    description: str = ""
    parameters: list[ToolParameter] = []

    def __init__(
        self,
        client: MCPClient,
        server_config: MCPServerConfig,
        tool_info: MCPToolInfo,
    ) -> None:
        # Set instance attributes *before* super().__init__ validation
        self.name = tool_info.name
        self.description = tool_info.description or f"MCP tool: {tool_info.name}"
        self.parameters = _schema_to_parameters(tool_info.input_schema)

        self._client = client
        self._server_config = server_config
        self._tool_info = tool_info

        super().__init__()

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Call the remote MCP tool and wrap the response."""
        try:
            async with self._client.connect(self._server_config) as session:
                raw = await self._client.call_tool(
                    session, self._tool_info.name, kwargs
                )
            # Try to parse JSON if the server returned a JSON string
            import json

            if isinstance(raw, str):
                try:
                    data = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    data = raw
            else:
                data = raw

            # Detect MCP-level errors
            if isinstance(data, dict) and data.get("status") == "error":
                return ToolResult.fail(
                    str(data.get("error") or data.get("message") or "MCP tool error"),
                    mcp_tool=self.name,
                )

            return ToolResult.ok(data, mcp_tool=self.name)

        except Exception as exc:
            return ToolResult.fail(f"MCP call failed: {exc}", mcp_tool=self.name)

    def __repr__(self) -> str:
        return f"<MCPBaseTool: {self.name} via {self._server_config.name}>"


async def discover_mcp_base_tools(
    url: str,
    server_name: str = "remote",
) -> list[MCPBaseTool]:
    """Connect to an MCP server, discover tools, and return them as BaseTools.

    Args:
        url: Streamable-HTTP URL of the MCP server.
        server_name: Logical name for the server.

    Returns:
        List of MCPBaseTool instances ready to be used by agents.
    """
    config = MCPServerConfig(
        name=server_name,
        transport="streamable-http",
        url=url,
    )
    return await discover_tools_from_config(config)


async def discover_tools_from_config(
    config: MCPServerConfig,
) -> list[MCPBaseTool]:
    """Connect to an MCP server described by *config* and discover its tools.

    Works with both ``streamable-http`` and ``stdio`` transports.
    """
    client = MCPClient()
    tools: list[MCPBaseTool] = []

    async with client.connect(config) as session:
        infos = await client.list_tools(session, config.name)
        for info in infos:
            tools.append(MCPBaseTool(client=client, server_config=config, tool_info=info))

    return tools


async def discover_all_configured_tools() -> list[MCPBaseTool]:
    """Load ``.aki/mcp.json`` and discover tools from every enabled server.

    Servers that fail to connect are silently skipped so one broken
    server doesn't block the rest.
    """
    from aki.mcp.config import load_mcp_configs

    configs = load_mcp_configs()
    all_tools: list[MCPBaseTool] = []

    for cfg in configs:
        try:
            tools = await discover_tools_from_config(cfg)
            all_tools.extend(tools)
        except Exception:
            # Skip unreachable servers — log in the future
            pass

    return all_tools
