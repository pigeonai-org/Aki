"""
OpenCLI Tool — structured bridge to the OpenCLI CLI hub.

Wraps `opencli` commands as a typed Aki tool so the LLM gets structured
parameters, JSON-parsed output, and meaningful error codes instead of raw
shell string manipulation.

Requires:
    npm install -g @jackwener/opencli
    A running browser with the OpenCLI bridge extension for site commands.

Exit-code semantics (from OpenCLI docs):
    0   — success
    1   — general error
    69  — browser / daemon not running
    77  — authentication required
    78  — adapter not found
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from typing import Any

from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_MAX_OUTPUT = 50_000  # truncate beyond this many chars
_DEFAULT_TIMEOUT = 60  # seconds


def _find_opencli() -> str | None:
    """Locate the opencli binary on PATH or via config."""
    try:
        from aki.config.settings import get_settings
        settings = get_settings()
        custom = getattr(settings, "opencli_path", None)
        if custom:
            return str(custom)
    except Exception:
        pass
    return shutil.which("opencli")


def _get_working_dir() -> str:
    """Return the sandbox directory (same logic as ShellTool)."""
    try:
        from aki.config.settings import get_settings
        sandbox = get_settings().sandbox_dir
        if sandbox:
            from pathlib import Path
            return str(Path(sandbox).expanduser().resolve())
    except Exception:
        pass
    return os.getcwd()


# ---------------------------------------------------------------------------
# Exit-code helpers
# ---------------------------------------------------------------------------

_EXIT_MESSAGES: dict[int, str] = {
    69: "Browser or OpenCLI daemon is not running. Try `opencli doctor` to diagnose.",
    77: "Authentication required — the target site needs a logged-in browser session.",
    78: "Adapter not found for the requested site/command.",
}


def _exit_hint(code: int) -> str:
    return _EXIT_MESSAGES.get(code, "")


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

@ToolRegistry.register
class OpenCLITool(BaseTool):
    """
    Execute OpenCLI commands to interact with websites, apps, and local tools.

    OpenCLI turns websites (Bilibili, Reddit, HackerNews, etc.), Electron apps,
    and local CLI tools into structured, scriptable commands with JSON output.

    Examples:
        site="bilibili"  command="hot"                     -> trending videos
        site="hackernews" command="top"                    -> top stories
        site="reddit"    command="search" args="rust lang" -> search Reddit
        site=""          command="list"   args="-f json"   -> list all adapters
        site=""          command="doctor"                   -> self-diagnose
    """

    name = "opencli"
    description = (
        "Run an OpenCLI command to fetch structured data from websites "
        "(Bilibili, Reddit, HackerNews, etc.), control the browser, or "
        "interact with local CLI tools. Returns JSON-parsed results when "
        "possible. Use site='' with command='list' to discover available "
        "adapters, or command='doctor' to diagnose connection issues."
    )
    parameters: list[ToolParameter] = [
        ToolParameter(
            name="site",
            type="string",
            description=(
                "Target site or adapter name (e.g. 'bilibili', 'reddit', "
                "'hackernews', 'github'). Leave empty for global commands "
                "like 'list' or 'doctor'."
            ),
            required=False,
            default="",
        ),
        ToolParameter(
            name="command",
            type="string",
            description=(
                "The sub-command to run (e.g. 'hot', 'search', 'top', "
                "'list', 'doctor'). Each site exposes different commands — "
                "use site='<name>' command='help' to discover them."
            ),
            required=True,
        ),
        ToolParameter(
            name="args",
            type="string",
            description=(
                "Additional arguments as a single string, passed verbatim "
                "after the command (e.g. search query, flags like '-f json', "
                "'--limit 20'). Optional."
            ),
            required=False,
            default="",
        ),
        ToolParameter(
            name="format",
            type="string",
            description=(
                "Output format flag appended as '-f <format>'. "
                "Defaults to 'json'. Set to '' to omit the flag."
            ),
            required=False,
            default="json",
            enum=["json", "text", "table", ""],
        ),
        ToolParameter(
            name="timeout",
            type="number",
            description="Timeout in seconds (default: 60, max: 300).",
            required=False,
            default=_DEFAULT_TIMEOUT,
        ),
    ]

    concurrency_safe = True  # multiple opencli calls can run in parallel

    async def execute(self, **kwargs: Any) -> ToolResult:
        # ------------------------------------------------------------------
        # 1. Resolve binary
        # ------------------------------------------------------------------
        binary = _find_opencli()
        if not binary:
            return ToolResult.fail(
                "opencli binary not found on PATH. "
                "Install with: npm install -g @jackwener/opencli"
            )

        # ------------------------------------------------------------------
        # 2. Build command string
        # ------------------------------------------------------------------
        site: str = (kwargs.get("site") or "").strip()
        command: str = (kwargs.get("command") or "").strip()
        args: str = (kwargs.get("args") or "").strip()
        fmt: str = (kwargs.get("format") or "json").strip()
        timeout: float = min(float(kwargs.get("timeout", _DEFAULT_TIMEOUT)), 300)

        if not command:
            return ToolResult.fail("'command' parameter is required.")

        parts: list[str] = [binary]
        if site:
            parts.append(site)
        parts.append(command)
        if args:
            parts.append(args)
        if fmt:
            parts.extend(["-f", fmt])

        cmd_str = " ".join(parts)
        cwd = _get_working_dir()

        logger.info("OpenCLI: %s (cwd=%s, timeout=%ss)", cmd_str, cwd, timeout)

        # ------------------------------------------------------------------
        # 3. Execute
        # ------------------------------------------------------------------
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd_str,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env={**os.environ},
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ToolResult.fail(
                    f"OpenCLI command timed out after {timeout}s. "
                    "The site may be slow or the daemon may be unresponsive."
                )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            exit_code = proc.returncode or 0

            # Truncate
            if len(stdout) > _MAX_OUTPUT:
                stdout = stdout[:_MAX_OUTPUT] + f"\n... (truncated, {len(stdout_bytes)} bytes total)"
            if len(stderr) > _MAX_OUTPUT:
                stderr = stderr[:_MAX_OUTPUT] + f"\n... (truncated, {len(stderr_bytes)} bytes total)"

        except Exception as e:
            return ToolResult.fail(f"Failed to execute opencli: {e}")

        # ------------------------------------------------------------------
        # 4. Parse output
        # ------------------------------------------------------------------
        parsed: Any = None
        if fmt == "json" and stdout.strip():
            try:
                parsed = json.loads(stdout)
            except json.JSONDecodeError:
                # Not valid JSON — fall back to raw text
                parsed = None

        data = parsed if parsed is not None else stdout

        # ------------------------------------------------------------------
        # 5. Return result
        # ------------------------------------------------------------------
        if exit_code != 0:
            hint = _exit_hint(exit_code)
            error_msg = f"OpenCLI exited with code {exit_code}"
            if hint:
                error_msg += f" — {hint}"
            if stderr:
                error_msg += f"\n[stderr] {stderr}"
            if not parsed and stdout:
                error_msg += f"\n[stdout] {stdout}"

            return ToolResult.fail(
                error_msg,
                data={
                    "exit_code": exit_code,
                    "stdout": data,
                    "stderr": stderr,
                    "command": cmd_str,
                },
            )

        # Build a human-readable summary for the LLM
        if isinstance(data, list):
            summary = f"OpenCLI returned {len(data)} items"
        elif isinstance(data, dict):
            summary = f"OpenCLI returned object with keys: {list(data.keys())[:10]}"
        else:
            text = str(data).strip()
            summary = text[:200] + ("..." if len(text) > 200 else "")

        return ToolResult.ok(
            data=data,
            summary=summary,
            command=cmd_str,
            exit_code=exit_code,
            stderr=stderr if stderr else None,
        )
