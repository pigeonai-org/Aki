"""
System restart tool.

Allows Aki to gracefully restart its own process — useful for applying
personality changes, config updates, or code hot-reloads.

How it works:
    1. Suspends all active sessions (persisted to disk)
    2. Replaces the current process via os.execv (same args)
    3. On restart, sessions rehydrate from JSONL automatically

This is a real process restart (PID changes), not a soft reload.
Sessions survive because they're persisted to .aki/sessions/.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@ToolRegistry.register
class SystemRestartTool(BaseTool):
    """Restart the Aki process. Sessions are preserved and will rehydrate on restart."""

    name = "system_restart"
    description = (
        "Restart the Aki process to apply changes (personality, config, code). "
        "All sessions are saved and will resume automatically after restart. "
        "Use with a reason so the user knows why you're restarting."
    )
    parameters: list[ToolParameter] = [
        ToolParameter(
            name="reason",
            type="string",
            description="Why the restart is needed (shown to the user before restarting).",
            required=True,
        ),
        ToolParameter(
            name="delay_seconds",
            type="number",
            description="Seconds to wait before restarting (default: 1). Gives time for the reply to be sent.",
            required=False,
            default=1,
        ),
    ]

    async def execute(self, **kwargs: Any) -> ToolResult:
        reason = kwargs.get("reason", "No reason given")
        delay = float(kwargs.get("delay_seconds", 1))

        logger.info("System restart requested: %s", reason)

        # 1. Suspend all active sessions
        try:
            from aki.memory.session.store import get_session_store
            store = get_session_store()
            for session in store.get_active_sessions():
                store.suspend(session.session_id)
                logger.info("Suspended session %s", session.session_id)
        except Exception as e:
            logger.warning("Failed to suspend sessions: %s", e)

        # 2. Schedule the restart after a short delay
        #    (so the tool result can be returned to the user first)
        import asyncio
        import threading

        def _do_restart() -> None:
            import time
            time.sleep(delay)

            # Reconstruct the original command
            argv = sys.argv[:]
            python = sys.executable

            logger.info("Restarting: %s %s", python, " ".join(argv))

            # Signal to the new process that this is a restart
            os.environ["AKI_RESTARTED"] = "1"

            # os.execv replaces the current process — no return
            try:
                os.execv(python, [python] + argv)
            except Exception as e:
                # If execv fails (shouldn't happen), log and exit
                logger.error("Failed to restart: %s", e)
                os._exit(1)

        # Run in a daemon thread so it doesn't block the response
        t = threading.Thread(target=_do_restart, daemon=True)
        t.start()

        return ToolResult.ok(
            data={
                "status": "restarting",
                "reason": reason,
                "delay_seconds": delay,
                "message": f"Restarting in {delay}s. Reason: {reason}",
            }
        )
