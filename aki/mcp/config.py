"""
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
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from aki.mcp.client.client import MCPServerConfig

_ENV_VAR_RE = re.compile(r"\$\{(\w+)\}")

_DEFAULT_CONFIG_PATH = ".aki/mcp.json"


def _interpolate_env(value: str) -> str:
    """Replace ``${VAR}`` placeholders with environment variable values."""
    def _replace(m: re.Match) -> str:
        return os.environ.get(m.group(1), "")
    return _ENV_VAR_RE.sub(_replace, value)


def _interpolate_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Recursively interpolate env vars in string values."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, str):
            out[k] = _interpolate_env(v)
        elif isinstance(v, dict):
            out[k] = _interpolate_dict(v)
        elif isinstance(v, list):
            out[k] = [_interpolate_env(i) if isinstance(i, str) else i for i in v]
        else:
            out[k] = v
    return out


def load_mcp_configs(config_path: str | Path | None = None) -> list[MCPServerConfig]:
    """Load MCP server configs from a JSON file.

    Args:
        config_path: Path to the config file.  Defaults to
            ``.aki/mcp.json`` relative to the current directory.

    Returns:
        List of ``MCPServerConfig`` ready for connection.  Returns an
        empty list if the file does not exist.
    """
    path = Path(config_path) if config_path else Path(_DEFAULT_CONFIG_PATH)
    path = path.expanduser().resolve()

    if not path.exists():
        return []

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    # Support both "mcpServers" (Claude Desktop / OpenClaw compat) and "servers"
    servers: dict[str, Any] = raw.get("mcpServers") or raw.get("servers") or {}
    configs: list[MCPServerConfig] = []

    for name, entry in servers.items():
        if not isinstance(entry, dict):
            continue

        # Resolve env vars
        entry = _interpolate_dict(entry)

        enabled = entry.get("enabled", True)
        if not enabled:
            continue

        transport = entry.get("transport", "stdio")
        configs.append(
            MCPServerConfig(
                name=name,
                transport=transport,
                url=entry.get("url"),
                command=entry.get("command", ""),
                args=entry.get("args", []),
                env=entry.get("env", {}),
            )
        )

    return configs
