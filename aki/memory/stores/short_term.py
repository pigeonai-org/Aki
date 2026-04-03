"""
Short-Term Memory Store

In-memory storage for current session memories.
Fast but not persistent across restarts.
"""

from collections import deque
from datetime import datetime
from typing import Optional

from aki.memory.base import MemoryItem, MemoryStore
from aki.memory.types import MemoryQuery


class ShortTermMemoryStore(MemoryStore):
    """
    In-memory short-term memory store.

    Stores memories in a list for fast access.
    Not persistent - cleared when the process ends.
    """

    _GLOBAL_TASK_KEY = "__global__"

    def __init__(
        self,
        max_size: int = 5000,
        max_items_per_task: int = 300,
    ):
        """
        Initialize the store.

        Args:
            max_size: Maximum number of memories across all tasks
            max_items_per_task: Maximum number of memories per task
        """
        self.max_size = max(1, max_size)
        self.max_items_per_task = max(1, max_items_per_task)
        self._memories: deque[MemoryItem] = deque()
        self._index: dict[str, MemoryItem] = {}
        self._task_index: dict[str, deque[str]] = {}
        self._id_to_task: dict[str, str] = {}

    @staticmethod
    def _task_key(task_id: Optional[str]) -> str:
        return task_id or ShortTermMemoryStore._GLOBAL_TASK_KEY

    def _remove_from_task_index(self, task_key: str, memory_id: str) -> None:
        task_queue = self._task_index.get(task_key)
        if task_queue is None:
            return
        try:
            task_queue.remove(memory_id)
        except ValueError:
            return
        if not task_queue:
            del self._task_index[task_key]

    def _remove_by_id(self, memory_id: str) -> None:
        item = self._index.pop(memory_id, None)
        if item is None:
            return

        task_key = self._id_to_task.pop(memory_id, self._GLOBAL_TASK_KEY)
        self._remove_from_task_index(task_key, memory_id)
        self._memories = deque(m for m in self._memories if m.id != memory_id)

    def _enforce_per_task_limit(self, task_key: str) -> None:
        task_queue = self._task_index.get(task_key)
        if task_queue is None:
            return
        while len(task_queue) > self.max_items_per_task:
            oldest_id = task_queue.popleft()
            self._id_to_task.pop(oldest_id, None)
            self._index.pop(oldest_id, None)
            self._memories = deque(m for m in self._memories if m.id != oldest_id)
        if not task_queue:
            del self._task_index[task_key]

    def _enforce_global_limit(self) -> None:
        while len(self._memories) > self.max_size:
            oldest = self._memories.popleft()
            self._index.pop(oldest.id, None)
            task_key = self._id_to_task.pop(oldest.id, self._GLOBAL_TASK_KEY)
            self._remove_from_task_index(task_key, oldest.id)

    async def add(self, item: MemoryItem) -> None:
        """Add a memory to the store."""
        task_key = self._task_key(item.task_id)
        self._memories.append(item)
        self._index[item.id] = item
        self._id_to_task[item.id] = task_key
        self._task_index.setdefault(task_key, deque()).append(item.id)

        self._enforce_per_task_limit(task_key)
        self._enforce_global_limit()

    async def get_recent(self, n: int) -> list[MemoryItem]:
        """Get the N most recent memories."""
        if n <= 0:
            return []
        return list(reversed(list(self._memories)[-n:]))  # Most recent first

    async def search(
        self,
        query: str,
        limit: int = 10,
    ) -> list[MemoryItem]:
        """
        Simple keyword search in memory content.

        For production, consider using vector similarity search.
        """
        if limit <= 0:
            return []
        query_lower = query.lower()
        matches: list[MemoryItem] = []

        for memory in reversed(self._memories):  # Most recent first
            if query_lower in memory.content.lower():
                matches.append(memory)
                if len(matches) >= limit:
                    break

        return matches

    async def get_by_task(self, task_id: str) -> list[MemoryItem]:
        """Get all memories for a task."""
        task_queue = self._task_index.get(self._task_key(task_id))
        if task_queue is None:
            return []
        items = [self._index[memory_id] for memory_id in task_queue if memory_id in self._index]
        return sorted(items, key=lambda m: m.timestamp, reverse=True)

    async def get_by_id(self, memory_id: str) -> Optional[MemoryItem]:
        """Get a memory by ID."""
        return self._index.get(memory_id)

    async def recall(self, query: MemoryQuery) -> list[MemoryItem]:
        """Structured retrieval with task/category filters."""
        if query.task_id:
            candidates = await self.get_by_task(query.task_id)
        else:
            candidates = await self.get_recent(self.max_size)

        if query.categories:
            candidates = [m for m in candidates if m.category in query.categories]

        if query.query:
            query_lower = query.query.lower()
            candidates = [m for m in candidates if query_lower in m.content.lower()]

        if query.now is not None:
            now = query.now
        else:
            now = datetime.now()
        candidates = [m for m in candidates if m.expires_at is None or m.expires_at > now]

        return candidates[: query.limit]

    async def clear(self) -> None:
        """Clear all memories."""
        self._memories.clear()
        self._index.clear()
        self._task_index.clear()
        self._id_to_task.clear()

    async def count(self) -> int:
        """Get total memory count."""
        return len(self._index)
