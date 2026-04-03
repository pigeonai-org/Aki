"""MCP Server module."""

from aki.mcp.server.adapter import MCPServerAdapter, create_mcp_server

# Real MCP server (requires mcp package)
try:
    from aki.mcp.server.server import (
        create_mcp_server_instance,
        run_mcp_server,
        main as run_server_main,
    )

    MCP_SERVER_AVAILABLE = True
except ImportError:
    MCP_SERVER_AVAILABLE = False

    def create_mcp_server_instance():
        return None

    async def run_mcp_server():
        raise ImportError("MCP SDK not installed")

    def run_server_main():
        raise ImportError("MCP SDK not installed")


__all__ = [
    # Adapter (always available)
    "MCPServerAdapter",
    "create_mcp_server",
    # Real MCP server (requires mcp package)
    "create_mcp_server_instance",
    "run_mcp_server",
    "run_server_main",
    "MCP_SERVER_AVAILABLE",
]
