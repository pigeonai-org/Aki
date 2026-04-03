"""
MCP module - Model Context Protocol server and client.

Aki operates as both:
- MCP Server: Exposes capabilities to Claude, Cursor, etc.
- MCP Client: Consumes tools from other MCP servers

Install the mcp package for full functionality:
    pip install mcp
"""

# Server exports
from aki.mcp.server import (
    MCPServerAdapter,
    create_mcp_server,
    MCP_SERVER_AVAILABLE,
)

# Client exports
from aki.mcp.client import (
    MCPClientManager,
    get_mcp_client,
    reset_mcp_client,
    is_mcp_available,
    MCP_CLIENT_AVAILABLE,
)

# Real MCP implementations (conditional)
if MCP_SERVER_AVAILABLE:
    from aki.mcp.server import (
        create_mcp_server_instance,
        run_mcp_server,
    )

if MCP_CLIENT_AVAILABLE:
    from aki.mcp.client import (
        MCPClient,
        MCPServerConfig,
        MCPToolInfo,
        MCPToolWrapper,
        discover_mcp_tools,
    )


def check_mcp_status() -> dict[str, bool]:
    """Check MCP SDK availability status."""
    return {
        "mcp_installed": is_mcp_available(),
        "server_available": MCP_SERVER_AVAILABLE,
        "client_available": MCP_CLIENT_AVAILABLE,
    }


__all__ = [
    # Always available
    "MCPServerAdapter",
    "create_mcp_server",
    "MCPClientManager",
    "get_mcp_client",
    "reset_mcp_client",
    # Status checks
    "check_mcp_status",
    "is_mcp_available",
    "MCP_SERVER_AVAILABLE",
    "MCP_CLIENT_AVAILABLE",
    # Conditional exports (only when mcp installed)
    "create_mcp_server_instance",
    "run_mcp_server",
    "MCPClient",
    "MCPServerConfig",
    "MCPToolInfo",
    "MCPToolWrapper",
    "discover_mcp_tools",
]
