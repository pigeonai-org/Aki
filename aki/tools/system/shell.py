"""
Shell execution tool.

Runs shell commands and returns stdout/stderr. Sandboxed to the configured
working directory (AKI_SANDBOX_DIR or CWD).

Security:
    - Commands run with the same permissions as the Aki process
    - Working directory is locked to the sandbox root
    - Timeout prevents runaway commands (default: 120s)
    - In Gateway/multi-user mode, restrict access via AKI_SANDBOX_DIR
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_MAX_OUTPUT = 50_000  # truncate output beyond this


def _get_working_dir() -> str:
    """Return the sandbox directory as the shell working directory."""
    try:
        from aki.config.settings import get_settings
        sandbox = get_settings().sandbox_dir
        if sandbox:
            return str(Path(sandbox).expanduser().resolve())
    except Exception:
        pass
    return os.getcwd()


@ToolRegistry.register
class ShellTool(BaseTool):
    """Execute a shell command and return its output."""

    name = "shell"
    description = (
        "Run a shell command (bash) and return stdout and stderr. "
        "The command runs in the configured working directory. "
        "Use for: installing packages, running scripts, git operations, "
        "system inspection, file manipulation, and any task that needs shell access."
    )
    parameters: list[ToolParameter] = [
        ToolParameter(
            name="command",
            type="string",
            description="The shell command to execute.",
            required=True,
        ),
        ToolParameter(
            name="timeout",
            type="number",
            description="Timeout in seconds (default: 120, max: 600).",
            required=False,
            default=120,
        ),
    ]

    async def execute(self, **kwargs: Any) -> ToolResult:
        command = kwargs.get("command", "")
        if not command:
            return ToolResult.fail("command parameter is required")

        timeout = min(float(kwargs.get("timeout", 120)), 600)
        cwd = _get_working_dir()

        logger.info("Shell: %s (cwd=%s, timeout=%ss)", command, cwd, timeout)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
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
                    f"Command timed out after {timeout}s. Process killed."
                )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            exit_code = proc.returncode or 0

            # Truncate very long output
            if len(stdout) > _MAX_OUTPUT:
                stdout = stdout[:_MAX_OUTPUT] + f"\n... (truncated, {len(stdout_bytes)} bytes total)"
            if len(stderr) > _MAX_OUTPUT:
                stderr = stderr[:_MAX_OUTPUT] + f"\n... (truncated, {len(stderr_bytes)} bytes total)"

            output = stdout
            if stderr:
                output = output + ("\n" if output else "") + f"[stderr]\n{stderr}"

            if exit_code != 0:
                return ToolResult.fail(
                    f"Exit code {exit_code}\n{output}",
                    data={"exit_code": exit_code, "stdout": stdout, "stderr": stderr},
                )

            return ToolResult.ok(
                data={"exit_code": exit_code, "stdout": stdout, "stderr": stderr},
                summary=output or "(no output)",
            )

        except Exception as e:
            return ToolResult.fail(f"Failed to execute command: {e}")
