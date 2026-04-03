"""Base class for memory dimension stores."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class DimensionStore(ABC):
    """Abstract base for a long-term memory dimension."""

    dimension: str  # "user", "episodic", etc.

    @abstractmethod
    def load(self, user_id: str) -> dict[str, Any]:
        """Load this dimension's data for a user. Returns structured data."""
        ...

    @abstractmethod
    def save(self, user_id: str, data: dict[str, Any]) -> None:
        """Persist this dimension's data for a user."""
        ...

    @abstractmethod
    def to_context(self, user_id: str) -> str:
        """Generate the context string to inject into the system prompt."""
        ...

    @abstractmethod
    def update(self, user_id: str, **kwargs: Any) -> None:
        """Update specific fields for this dimension."""
        ...
