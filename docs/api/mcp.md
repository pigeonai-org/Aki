# `aki.mcp` API 文档

> MCP 协议支持 — MCP 客户端/服务端、Tool↔MCP 双向适配

---

## `aki.mcp.config`

**文件路径：** `aki/mcp/config.py`

MCP server configuration loader.

Reads `.aki/mcp.json` to discover which MCP servers should be
connected at session start.  Supports both streamable-http and stdio
transports.

Config format (`.aki/mcp.json`):

    {
      "mcpServers": {
        "dating": {
          "transport": "streamable-http",
          "url": "http://127.0.0.1:8000/mcp"
        },
        "discord": {
          "transport": "stdio",
          "command": "npx",
          "args": ["-y", "mcp-discord"],
          "env": {
            "DISCORD_TOKEN": "${DISCORD_TOKEN}"
          }
        }
      }
    }

Compatible with Claude Desktop / OpenClaw ``mcpServers`` format.
Also accepts legacy ``servers`` key for backwards compatibility.

Environment variable interpolation: values like ``${VAR}`` are replaced
with the corresponding environment variable at load time.
---

#### `def load_mcp_configs(config_path: str | Path | None = None) -> list[MCPServerConfig]` <small>(L71)</small>

Load MCP server configs from a JSON file.

Args:
    config_path: Path to the config file.  Defaults to
        ``.aki/mcp.json`` relative to the current directory.

Returns:
    List of ``MCPServerConfig`` ready for connection.  Returns an
    empty list if the file does not exist.



---

## `aki.mcp.client.adapter`

**文件路径：** `aki/mcp/client/adapter.py`

MCP-to-BaseTool Adapter

Bridges MCP tools into Aki's BaseTool system so that agents
can call remote MCP server tools through the standard ReAct loop.
---

#### class `MCPBaseTool(BaseTool)`

```
A BaseTool that delegates execution to a remote MCP server tool.

Each ``execute()`` call opens a fresh connection to the MCP server,
calls the tool, and returns a ``ToolResult``.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `str` | `'__mcp_placeholder__'` |  |
| `description` | `str` | `''` |  |
| `parameters` | `list[ToolParameter]` | `[]` |  |

**方法：**

##### `def __init__(self, client: MCPClient, server_config: MCPServerConfig, tool_info: MCPToolInfo) -> None` <small>(L61)</small>

##### `async def execute(self, **kwargs: Any) -> ToolResult` <small>(L78)</small>

Call the remote MCP tool and wrap the response.

##### `def __repr__(self) -> str` <small>(L108)</small>


---

#### `async def discover_mcp_base_tools(url: str, server_name: str = 'remote') -> list[MCPBaseTool]` <small>(L112)</small>

Connect to an MCP server, discover tools, and return them as BaseTools.

Args:
    url: Streamable-HTTP URL of the MCP server.
    server_name: Logical name for the server.

Returns:
    List of MCPBaseTool instances ready to be used by agents.


---

#### `async def discover_tools_from_config(config: MCPServerConfig) -> list[MCPBaseTool]` <small>(L133)</small>

Connect to an MCP server described by *config* and discover its tools.

Works with both ``streamable-http`` and ``stdio`` transports.


---

#### `async def discover_all_configured_tools() -> list[MCPBaseTool]` <small>(L151)</small>

Load ``.aki/mcp.json`` and discover tools from every enabled server.

Servers that fail to connect are silently skipped so one broken
server doesn't block the rest.



---

## `aki.mcp.client.client`

**文件路径：** `aki/mcp/client/client.py`

MCP Client Implementation

Real MCP client using the official MCP Python SDK.
Allows Aki agents to call tools from external MCP servers.
---

#### class `MCPServerConfig(BaseModel)`

```
Configuration for connecting to an MCP server.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `str` | `` | Server name for identification |
| `command` | `str` | `''` | Command to start the server (stdio transport) |
| `args` | `list[str]` | `` | Command arguments |
| `env` | `dict[str, str]` | `` | Environment variables |
| `url` | `str | None` | `None` | HTTP URL for streamable HTTP transport |
| `transport` | `str` | `'stdio'` | Transport type:  |


---

#### class `MCPToolInfo(BaseModel)`

```
Information about an MCP tool.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `str` | `` |  |
| `description` | `str` | `` |  |
| `input_schema` | `dict[str, Any]` | `` |  |


---

#### class `MCPClient`

```
MCP Client for connecting to external MCP servers.

Allows Aki to use tools from other MCP-compatible services.
```

**方法：**

##### `def __init__(self)` <small>(L54)</small>

Initialize the MCP client.

##### `async def connect(self, config: MCPServerConfig) -> AsyncIterator['ClientSession']` <small>(L65)</small>

Connect to an MCP server.

Args:
    config: Server configuration

Yields:
    MCP ClientSession

##### `async def list_tools(self, session: 'ClientSession', server_name: str) -> list[MCPToolInfo]` <small>(L103)</small>

List available tools from an MCP server.

Args:
    session: Active MCP session
    server_name: Server name for caching

Returns:
    List of available tools

##### `async def call_tool(self, session: 'ClientSession', tool_name: str, arguments: dict[str, Any]) -> Any` <small>(L137)</small>

Call a tool on an MCP server.

Args:
    session: Active MCP session
    tool_name: Name of the tool to call
    arguments: Tool arguments

Returns:
    Tool result


---

#### class `MCPToolWrapper`

```
Wrapper to use MCP tools as Aki tools.

Bridges external MCP tools into the Aki tool system.
```

**方法：**

##### `def __init__(self, client: MCPClient, server_config: MCPServerConfig, tool_info: MCPToolInfo)` <small>(L174)</small>

Initialize the wrapper.

Args:
    client: MCP client instance
    server_config: Server configuration
    tool_info: Tool information

##### `async def execute(self, **kwargs: Any) -> dict[str, Any]` <small>(L196)</small>

Execute the MCP tool.

Args:
    **kwargs: Tool arguments

Returns:
    Tool result

##### `def to_openai_schema(self) -> dict[str, Any]` <small>(L212)</small>

Convert to OpenAI function calling format.


---

#### `async def discover_mcp_tools(config: MCPServerConfig) -> list[MCPToolWrapper]` <small>(L224)</small>

Discover and wrap all tools from an MCP server.

Args:
    config: Server configuration

Returns:
    List of wrapped tools


---

#### `def is_mcp_available() -> bool` <small>(L250)</small>

Check if MCP SDK is installed.



---

## `aki.mcp.client.manager`

**文件路径：** `aki/mcp/client/manager.py`

MCP Client Manager

Manages connections to external MCP servers.
Allows Aki agents to use tools from other MCP providers.
---

#### class `MCPServerConfig(BaseModel)`

```
Configuration for an MCP server connection.
```

**属性：**

| 属性名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `name` | `str` | `` | Server name |
| `command` | `Optional[str]` | `None` | Command to start the server (for stdio transport) |
| `args` | `list[str]` | `` | Command arguments |
| `url` | `Optional[str]` | `None` | Server URL (for SSE transport) |
| `env` | `dict[str, str]` | `` | Environment variables |


---

#### class `MCPClientManager`

```
MCP Client Manager.

Manages connections to external MCP servers and provides
a unified interface for calling their tools.
```

**方法：**

##### `def __init__(self)` <small>(L43)</small>

Initialize the client manager.

##### `def register_server(self, config: MCPServerConfig) -> None` <small>(L49)</small>

Register an MCP server.

Args:
    config: Server configuration

##### `async def connect(self, server_name: str) -> bool` <small>(L58)</small>

Connect to an MCP server.

Args:
    server_name: Name of the server to connect to

Returns:
    True if connection successful

##### `async def disconnect(self, server_name: str) -> None` <small>(L82)</small>

Disconnect from an MCP server.

Args:
    server_name: Name of the server to disconnect from

##### `async def list_tools(self, server_name: str) -> list[dict[str, Any]]` <small>(L94)</small>

List available tools from an MCP server.

Args:
    server_name: Name of the server

Returns:
    List of tool definitions

##### `async def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]` <small>(L117)</small>

Call a tool on an MCP server.

Args:
    server_name: Name of the server
    tool_name: Name of the tool
    arguments: Tool arguments

Returns:
    Tool result

##### `def list_servers(self) -> list[str]` <small>(L147)</small>

List all registered servers.

##### `def is_connected(self, server_name: str) -> bool` <small>(L151)</small>

Check if connected to a server.


---

#### `def get_mcp_client() -> MCPClientManager` <small>(L160)</small>

Get the global MCP client manager instance (singleton).


---

#### `def reset_mcp_client() -> None` <small>(L168)</small>

Reset the global MCP client manager instance.



---

## `aki.mcp.server.adapter`

**文件路径：** `aki/mcp/server/adapter.py`

MCP Server Adapter

Exposes Aki capabilities as an MCP server.
Allows Claude, Cursor, and other MCP clients to use Aki tools.
---

#### class `MCPServerAdapter`

```
MCP Server Adapter.

Wraps Aki functionality as MCP tools that can be called
by MCP clients (Claude, Cursor, etc.).
```

**方法：**

##### `def __init__(self, orchestrator: Optional[AgentOrchestrator] = None)` <small>(L24)</small>

Initialize the MCP server adapter.

Args:
    orchestrator: Agent orchestrator (uses global if not provided)

##### `def get_tools(self) -> list[dict[str, Any]]` <small>(L137)</small>

Get all available MCP tools.

Returns:
    List of tool definitions in MCP format

##### `async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]` <small>(L146)</small>

Call an MCP tool.

Args:
    name: Tool name
    arguments: Tool arguments

Returns:
    Tool result


---

#### `def create_mcp_server() -> MCPServerAdapter` <small>(L235)</small>

Create an MCP server adapter instance.



---

## `aki.mcp.server.server`

**文件路径：** `aki/mcp/server/server.py`

MCP Server Implementation

Real MCP server using the official MCP Python SDK.
Exposes Aki capabilities as an MCP server.
---

#### `def create_mcp_server_instance() -> 'Server | None'` <small>(L42)</small>

Create a real MCP server instance.

Returns:
    MCP Server instance, or None if MCP SDK not installed


---

#### `async def run_mcp_server() -> None` <small>(L265)</small>

Run the MCP server using stdio transport.

This is the main entry point for running Aki as an MCP server.


---

#### `def main() -> None` <small>(L288)</small>

Entry point for MCP server.



---

