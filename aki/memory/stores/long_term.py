"""
Long-Term Memory Store

File-based persistent storage for memories across sessions.
Uses JSON for simplicity - can be upgraded to database later.
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from aki.memory.base import MemoryItem, MemoryStore
from aki.memory.types import MemoryQuery


class LongTermMemoryStore(MemoryStore):
    """
    File-based long-term memory store.

    Persists memories to JSON files for durability.
    Simple implementation for MVP - consider SQLite/PostgreSQL for production.
    """

    def __init__(self, persist_dir: str = "./data/memory"):
        """
        Initialize the store.

        Args:
            persist_dir: Directory for memory files
        """
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._memories_file = self.persist_dir / "memories.json"
        self._memories: list[MemoryItem] = []
        self._loaded = False

    async def _load(self) -> None:
        """Load memories from disk."""
        if self._loaded:
            return

        if self._memories_file.exists():
            try:
                with open(self._memories_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for m in data:
                        if isinstance(m.get("timestamp"), str):
                            m["timestamp"] = datetime.fromisoformat(m["timestamp"])
                        if isinstance(m.get("expires_at"), str):
                            m["expires_at"] = datetime.fromisoformat(m["expires_at"])
                    self._memories = [MemoryItem(**m) for m in data]
            except (json.JSONDecodeError, KeyError):
                self._memories = []

        self._loaded = True

    async def _save(self) -> None:
        """Save memories to disk atomically."""
        data = [item.model_dump() for item in self._memories]
        # Convert datetime objects to ISO strings
        for entry in data:
            for key in ("timestamp", "expires_at"):
                if isinstance(entry.get(key), datetime):
                    entry[key] = entry[key].isoformat()
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(self._memories_file.parent), suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(data, f, default=str)
            os.replace(tmp_path, str(self._memories_file))
        except BaseException:
            os.unlink(tmp_path)
            raise

    async def add(self, item: MemoryItem) -> None:
        """Add a memory to the store."""
        await self._load()
        if item.fingerprint:
            self._memories = [
                memory
                for memory in self._memories
                if not (
                    memory.fingerprint == item.fingerprint
                    and memory.namespace == item.namespace
                    and memory.category == item.category
                )
            ]
        self._memories.append(item)
        await self._save()

    async def get_recent(self, n: int) -> list[MemoryItem]:
        """Get the N most recent memories."""
        await self._load()
        sorted_memories = sorted(
            self._memories,
            key=lambda m: m.timestamp,
            reverse=True,
        )
        return sorted_memories[:n]

    async def search(
        self,
        query: str,
        limit: int = 10,
    ) -> list[MemoryItem]:
        """Simple keyword search in memory content."""
        await self._load()
        query_lower = query.lower()
        matches = []

        sorted_memories = sorted(
            self._memories,
            key=lambda m: m.timestamp,
            reverse=True,
        )

        for memory in sorted_memories:
            if query_lower in memory.content.lower():
                matches.append(memory)
                if len(matches) >= limit:
                    break

        return matches

    async def search_semantic(self, query: MemoryQuery) -> list[MemoryItem]:
        """
        Fallback structured retrieval for stores without vector search.
        """
        await self._load()
        now = query.now or datetime.now()

        if query.query:
            candidates = await self.search(query.query, query.limit * 3)
        else:
            candidates = await self.get_recent(query.limit * 3)

        filtered: list[MemoryItem] = []
        for item in candidates:
            if item.namespace != query.namespace:
                continue
            if query.categories and item.category not in query.categories:
                continue
            if query.task_id and item.task_id != query.task_id:
                continue
            if not query.include_expired and item.expires_at and item.expires_at <= now:
                continue
            filtered.append(item)
            if len(filtered) >= query.limit:
                break

        return filtered

    async def get_by_task(self, task_id: str) -> list[MemoryItem]:
        """Get all memories for a task."""
        await self._load()
        return [m for m in self._memories if m.task_id == task_id]

    async def get_by_id(self, memory_id: str) -> Optional[MemoryItem]:
        """Get a memory by ID."""
        await self._load()
        for m in self._memories:
            if m.id == memory_id:
                return m
        return None

    async def clear(self) -> None:
        """Clear all memories."""
        self._memories.clear()
        if self._memories_file.exists():
            self._memories_file.unlink()
        self._loaded = True

    async def count(self) -> int:
        """Get total memory count."""
        await self._load()
        return len(self._memories)

    async def prune_expired(self, now: Optional[datetime] = None) -> int:
        """Remove expired memories and persist the change."""
        await self._load()
        cutoff = now or datetime.now()
        before = len(self._memories)
        self._memories = [m for m in self._memories if not (m.expires_at and m.expires_at <= cutoff)]
        removed = before - len(self._memories)
        if removed:
            await self._save()
        return removed
