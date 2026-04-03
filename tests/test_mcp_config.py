"""Unit tests for MCP config file loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aki.mcp.config import load_mcp_configs, _interpolate_env


def test_load_empty_when_file_missing(tmp_path: Path):
    configs = load_mcp_configs(tmp_path / "nonexistent.json")
    assert configs == []


def test_load_http_server(tmp_path: Path):
    cfg_file = tmp_path / "mcp.json"
    cfg_file.write_text(json.dumps({
        "mcpServers": {
            "dating": {
                "transport": "streamable-http",
                "url": "http://localhost:8000/mcp",
            }
        }
    }))
    configs = load_mcp_configs(cfg_file)
    assert len(configs) == 1
    assert configs[0].name == "dating"
    assert configs[0].transport == "streamable-http"
    assert configs[0].url == "http://localhost:8000/mcp"


def test_load_stdio_server(tmp_path: Path):
    cfg_file = tmp_path / "mcp.json"
    cfg_file.write_text(json.dumps({
        "mcpServers": {
            "discord": {
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "mcp-discord"],
                "env": {"DISCORD_TOKEN": "test-token"},
            }
        }
    }))
    configs = load_mcp_configs(cfg_file)
    assert len(configs) == 1
    assert configs[0].name == "discord"
    assert configs[0].command == "npx"
    assert configs[0].args == ["-y", "mcp-discord"]
    assert configs[0].env == {"DISCORD_TOKEN": "test-token"}


def test_env_var_interpolation(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MY_SECRET", "s3cret")
    assert _interpolate_env("${MY_SECRET}") == "s3cret"
    assert _interpolate_env("prefix-${MY_SECRET}-suffix") == "prefix-s3cret-suffix"
    assert _interpolate_env("no-vars-here") == "no-vars-here"


def test_env_var_in_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BOT_TOKEN", "abc123")
    cfg_file = tmp_path / "mcp.json"
    cfg_file.write_text(json.dumps({
        "mcpServers": {
            "bot": {
                "transport": "stdio",
                "command": "node",
                "args": ["server.js"],
                "env": {"TOKEN": "${BOT_TOKEN}"},
            }
        }
    }))
    configs = load_mcp_configs(cfg_file)
    assert configs[0].env["TOKEN"] == "abc123"


def test_disabled_server_skipped(tmp_path: Path):
    cfg_file = tmp_path / "mcp.json"
    cfg_file.write_text(json.dumps({
        "mcpServers": {
            "active": {"transport": "streamable-http", "url": "http://a"},
            "disabled": {"transport": "streamable-http", "url": "http://b", "enabled": False},
        }
    }))
    configs = load_mcp_configs(cfg_file)
    assert len(configs) == 1
    assert configs[0].name == "active"


def test_multiple_servers(tmp_path: Path):
    cfg_file = tmp_path / "mcp.json"
    cfg_file.write_text(json.dumps({
        "mcpServers": {
            "a": {"transport": "streamable-http", "url": "http://a/mcp"},
            "b": {"transport": "stdio", "command": "npx", "args": ["-y", "some-mcp"]},
        }
    }))
    configs = load_mcp_configs(cfg_file)
    assert len(configs) == 2
    names = {c.name for c in configs}
    assert names == {"a", "b"}
