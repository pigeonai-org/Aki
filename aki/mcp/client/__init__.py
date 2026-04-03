"""MCP Client module."""

# Real MCP client (requires mcp package)
try:
    from aki.mcp.client.client import (
        MCPClient,
        MCPServerConfig,
        MCPToolInfo,
        MCPToolWrapper,
        discover_mcp_tools,
        is_mcp_available,
    )

    MCP_CLIENT_AVAILABLE = True
except ImportError:
    MCP_CLIENT_AVAILABLE = False

    def is_mcp_available():
        return False


# Backward-compat aliases for code that imported from the old manager module
MCPClientManager = MCPClient if MCP_CLIENT_AVAILABLE else None  # type: ignore[assignment,misc]


def get_mcp_client() -> "MCPClient":
    """Return a new MCPClient instance (replaces legacy singleton)."""
    if not MCP_CLIENT_AVAILABLE:
        raise ImportError("mcp package is not installed")
    return MCPClient()


def reset_mcp_client() -> None:
    """No-op kept for backward compatibility."""
    pass


__all__ = [
    # Backward-compat
    "MCPClientManager",
    "get_mcp_client",
    "reset_mcp_client",
    # Real MCP client (requires mcp package)
    "MCPClient",
    "MCPServerConfig",
    "MCPToolInfo",
    "MCPToolWrapper",
    "discover_mcp_tools",
    "is_mcp_available",
    "MCP_CLIENT_AVAILABLE",
]
