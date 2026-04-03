"""
Async Input Reader

Reads stdin in a thread executor so the asyncio event loop is never blocked.
Emits USER_INPUT events to the UIEventBus.

Renders a Claude Code-style input area with separator lines and ❯ prompt.
"""

import asyncio
import shutil
import sys

from aki.cli.events import UIEvent, UIEventBus, UIEventType

# ANSI codes
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RESET = "\033[0m"
_BLUE = "\033[34m"


class AsyncInputReader:
    """Non-blocking stdin reader with Claude Code-style bordered input area."""

    def __init__(self, event_bus: UIEventBus, prompt: str = "❯ ") -> None:
        self._bus = event_bus
        self._prompt = prompt
        self._running = True
        self._first = True

    async def run(self) -> None:
        """Main loop — runs until stop() is called or EOF."""
        loop = asyncio.get_event_loop()
        while self._running:
            try:
                line = await loop.run_in_executor(None, self._read_line)
            except (EOFError, KeyboardInterrupt):
                break
            if line is None:
                break
            text = line.strip()
            if text:
                self._bus.emit_nowait(UIEvent(type=UIEventType.USER_INPUT, data={"text": text}))

    def _read_line(self) -> str | None:
        """Blocking readline in thread. Returns None on EOF."""
        try:
            width = shutil.get_terminal_size().columns
            sep = _DIM + "─" * width + _RESET

            if self._first:
                sys.stdout.write(sep + "\n")
                self._first = False
            else:
                sys.stdout.write(sep + "\n")

            sys.stdout.write(f"{_BOLD}❯{_RESET} ")
            sys.stdout.flush()
            line = sys.stdin.readline()
            if not line:  # EOF
                return None

            # Print bottom separator after input
            sys.stdout.write(sep + "\n")
            sys.stdout.flush()
            return line
        except (EOFError, OSError):
            return None

    def stop(self) -> None:
        """Signal the reader to stop after the current readline."""
        self._running = False
