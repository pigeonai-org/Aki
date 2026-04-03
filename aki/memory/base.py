"""
Memory Base Classes

Memory system for storing and retrieving agent memories.
Separate from Knowledge (static domain knowledge) - Memory is for dynamic session data.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from aki.memory.types import (
    MemoryCategory,
    MemoryQuery,
    MemoryScope,
    normalize_category,
    normalize_scope,
)


class MemoryItem(BaseModel):
    """
    A single memory unit.

    Stores observations, actions, results, and thoughts from agent execution.
    """

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for this memory",
    )
    content: str = Field(..., description="Memory content")
    type: str = Field(
        default=MemoryCategory.TASK_EVENT.value,
        description="Legacy memory type label retained for backward compatibility",
    )
    category: MemoryCategory = Field(
        default=MemoryCategory.TASK_EVENT,
        description="Canonical memory category",
    )
    scope: MemoryScope = Field(
        default=MemoryScope.SHORT_TERM,
        description="Memory scope: short_term or long_term",
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When this memory was created",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata",
    )
    importance: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Importance score for filtering (0.0-1.0)",
    )
    agent_id: Optional[str] = Field(
        default=None,
        description="ID of the agent that created this memory",
    )
    task_id: Optional[str] = Field(
        default=None,
        description="ID of the task this memory belongs to",
    )
    namespace: str = Field(
        default="default",
        description="Namespace identifier for long-term memory separation",
    )
    expires_at: Optional[datetime] = Field(
        default=None,
        description="Optional expiry timestamp (mainly for long-term memory)",
    )
    source_uri: Optional[str] = Field(
        default=None,
        description="Optional source URI, usually for web/domain memory",
    )
    fingerprint: Optional[str] = Field(
        default=None,
        description="Stable fingerprint used for deduplication/upsert",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        normalized_data = dict(data)
        raw_category = normalized_data.get("category", normalized_data.get("type"))
        category = normalize_category(raw_category, default=MemoryCategory.TASK_EVENT)
        scope = normalize_scope(normalized_data.get("scope"), default=MemoryScope.SHORT_TERM)

        normalized_data["category"] = category
        normalized_data["type"] = str(normalized_data.get("type") or category.value)
        normalized_data["scope"] = scope
        if not normalized_data.get("namespace"):
            normalized_data["namespace"] = "default"
        return normalized_data


class MemoryStrategy(ABC):
    """
    Abstract base class for memory selection strategies.

    Strategies determine which memories to keep/return when limits are reached.
    """

    @abstractmethod
    def select(
        self,
        memories: list[MemoryItem],
        limit: int,
    ) -> list[MemoryItem]:
        """
        Select memories to keep/return.

        Args:
            memories: All available memories
            limit: Maximum number to return

        Returns:
            Selected memories
        """
        pass


class MemoryStore(ABC):
    """
    Abstract base class for memory storage.

    Implementations can use in-memory, file, or database storage.
    """

    @abstractmethod
    async def add(self, item: MemoryItem) -> None:
        """
        Add a memory item to the store.

        Args:
            item: Memory to add
        """
        pass

    @abstractmethod
    async def get_recent(self, n: int) -> list[MemoryItem]:
        """
        Get the N most recent memories.

        Args:
            n: Number of memories to retrieve

        Returns:
            List of recent memories
        """
        pass

    @abstractmethod
    async def search(
        self,
        query: str,
        limit: int = 10,
    ) -> list[MemoryItem]:
        """
        Search memories by query.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            Matching memories
        """
        pass

    async def search_semantic(
        self,
        query: MemoryQuery,
    ) -> list[MemoryItem]:
        """
        Optional semantic search interface.

        Stores that don't support semantic scoring should override this as needed.
        Default behavior falls back to keyword search.
        """
        if query.query is None:
            return await self.get_recent(query.limit)
        return await self.search(query.query, query.limit)

    @abstractmethod
    async def get_by_task(self, task_id: str) -> list[MemoryItem]:
        """
        Get all memories for a task.

        Args:
            task_id: Task ID

        Returns:
            Memories for the task
        """
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all memories."""
        pass

    @abstractmethod
    async def count(self) -> int:
        """Get total memory count."""
        pass

    async def prune_expired(self, now: Optional[datetime] = None) -> int:
        """
        Optional TTL pruning hook.

        Returns:
            Number of records removed.
        """
        del now
        return 0
