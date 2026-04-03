"""
Shared Task Memory

In-memory key-value store shared between agents working on the same task.
Replaces the hacky _last_media_extractor_output / _last_localized_output
instance variables in DelegateToWorkerTool.
"""

import asyncio
import logging
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)


class SharedTaskMemory:
    """
    Shared state between agents working on the same task.

    Each task gets an isolated namespace keyed by task_id.
    Thread-safe via asyncio.Lock per task.

    Usage::

        shared = SharedTaskMemory()

        # Agent 1 stores transcription result
        await shared.set("task_abc", "transcription", {"segments": [...]})

        # Agent 2 reads it
        transcription = await shared.get("task_abc", "transcription")

        # Cleanup when task is done
        await shared.clear_task("task_abc")
    """

    def __init__(self) -> None:
        self._stores: dict[str, dict[str, Any]] = defaultdict(dict)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def get(self, task_id: str, key: str, default: Any = None) -> Any:
        """
        Get a value from the task's shared state.

        Args:
            task_id: The task identifier.
            key: The state key.
            default: Value to return if key is not found.

        Returns:
            The stored value, or default if not found.
        """
        async with self._locks[task_id]:
            return self._stores[task_id].get(key, default)

    async def set(self, task_id: str, key: str, value: Any) -> None:
        """
        Set a value in the task's shared state.

        Args:
            task_id: The task identifier.
            key: The state key.
            value: The value to store.
        """
        async with self._locks[task_id]:
            self._stores[task_id][key] = value
            logger.debug("SharedTaskMemory: set %s.%s", task_id[:8], key)

    async def get_all(self, task_id: str) -> dict[str, Any]:
        """Get all key-value pairs for a task."""
        async with self._locks[task_id]:
            return dict(self._stores[task_id])

    async def has(self, task_id: str, key: str) -> bool:
        """Check if a key exists in the task's shared state."""
        async with self._locks[task_id]:
            return key in self._stores[task_id]

    async def delete(self, task_id: str, key: str) -> bool:
        """
        Delete a key from the task's shared state.

        Returns:
            True if the key existed, False otherwise.
        """
        async with self._locks[task_id]:
            if key in self._stores[task_id]:
                del self._stores[task_id][key]
                return True
            return False

    async def keys(self, task_id: str) -> list[str]:
        """List all keys in the task's shared state."""
        async with self._locks[task_id]:
            return list(self._stores[task_id].keys())

    async def clear_task(self, task_id: str) -> None:
        """Remove all shared state for a task."""
        async with self._locks[task_id]:
            self._stores.pop(task_id, None)
        self._locks.pop(task_id, None)
        logger.debug("SharedTaskMemory: cleared task %s", task_id[:8])

    async def update(self, task_id: str, data: dict[str, Any]) -> None:
        """
        Merge multiple key-value pairs into the task's shared state.

        Args:
            task_id: The task identifier.
            data: Dict of key-value pairs to merge.
        """
        async with self._locks[task_id]:
            self._stores[task_id].update(data)

    @property
    def active_tasks(self) -> list[str]:
        """List task_ids with active shared state."""
        return list(self._stores.keys())
