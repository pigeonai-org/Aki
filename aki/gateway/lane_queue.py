"""Per-session serialization queue using asyncio.Lock.

Guarantees that at most one agent turn runs per session at a time,
preventing concurrent state corruption in UniversalAgent.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator


class LaneQueue:
    """Ensures at most one agent turn runs per session at a time.

    Each session gets its own ``asyncio.Lock``.  When a second message
    arrives while the first is still processing, it ``await`` s on the
    lock and executes sequentially — no interleaving of ``run_turn()``
    calls on the same ``UniversalAgent`` instance.
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._pending: dict[str, int] = {}

    def _get_lock(self, session_id: str) -> asyncio.Lock:
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        return self._locks[session_id]

    @asynccontextmanager
    async def acquire(self, session_id: str) -> AsyncIterator[None]:
        """Acquire exclusive access to a session lane.

        Usage::

            async with lane_queue.acquire(session_id):
                await session_manager.send_message(session_id, text)
        """
        lock = self._get_lock(session_id)
        self._pending[session_id] = self._pending.get(session_id, 0) + 1
        try:
            async with lock:
                yield
        finally:
            self._pending[session_id] -= 1
            if self._pending[session_id] <= 0:
                self._pending.pop(session_id, None)

    def pending_count(self, session_id: str) -> int:
        """Return the number of messages waiting (including the active one)."""
        return self._pending.get(session_id, 0)

    def cleanup(self, session_id: str) -> None:
        """Remove lock state for a session that has been destroyed."""
        self._locks.pop(session_id, None)
        self._pending.pop(session_id, None)
