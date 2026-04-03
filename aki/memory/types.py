"""
Memory typing helpers.

Defines canonical memory scopes/categories and common query parameters.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MemoryScope(str, Enum):
    """Scope for a memory record."""

    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"


class MemoryDimension(str, Enum):
    """Long-term memory dimensions (Layer 2+)."""

    USER = "user"              # Who the user is
    EPISODIC = "episodic"      # What happened in past sessions
    SEMANTIC = "semantic"      # Learned knowledge/facts
    PERSONA = "persona"        # Relationship & trait evolution
    PROCEDURAL = "procedural"  # User's work preferences/patterns


class SessionState(str, Enum):
    """Lifecycle state for a session."""

    ACTIVE = "active"
    DORMANT = "dormant"    # On disk, not in memory
    ARCHIVED = "archived"  # Review done, promoted to L2


class MemoryCategory(str, Enum):
    """Canonical memory category values."""

    # Primary categories
    TASK_EVENT = "task_event"
    MULTIMODAL_ARTIFACT = "multimodal_artifact"
    USER_INSTRUCTION = "user_instruction"
    DOMAIN_KNOWLEDGE = "domain_knowledge"
    WEB_KNOWLEDGE = "web_knowledge"

    # Backward-compatible legacy categories
    OBSERVATION = "observation"
    ACTION = "action"
    RESULT = "result"
    THOUGHT = "thought"


LONG_TERM_CATEGORIES: set[MemoryCategory] = {
    MemoryCategory.USER_INSTRUCTION,
    MemoryCategory.DOMAIN_KNOWLEDGE,
    MemoryCategory.WEB_KNOWLEDGE,
}


def normalize_category(
    value: Optional[str | MemoryCategory],
    *,
    default: MemoryCategory = MemoryCategory.TASK_EVENT,
) -> MemoryCategory:
    """Normalize arbitrary category strings into canonical enum values."""
    if value is None:
        return default
    if isinstance(value, MemoryCategory):
        return value

    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    try:
        return MemoryCategory(normalized)
    except ValueError:
        return default


def normalize_scope(
    value: Optional[str | MemoryScope],
    *,
    default: MemoryScope = MemoryScope.SHORT_TERM,
) -> MemoryScope:
    """Normalize scope strings into canonical enum values."""
    if value is None:
        return default
    if isinstance(value, MemoryScope):
        return value
    normalized = value.strip().lower()
    try:
        return MemoryScope(normalized)
    except ValueError:
        return default


class MemoryQuery(BaseModel):
    """Structured query object for memory retrieval."""

    query: Optional[str] = Field(default=None, description="Semantic/keyword query")
    limit: int = Field(default=10, ge=1, description="Maximum number of memories to return")
    task_id: Optional[str] = Field(default=None, description="Restrict search to a task id")
    namespace: str = Field(default="default", description="Namespace for long-term memory")
    categories: Optional[set[MemoryCategory]] = Field(
        default=None, description="Filter by memory categories"
    )
    scope: Optional[MemoryScope] = Field(default=None, description="Target memory scope")
    min_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Minimum relevance score")
    include_expired: bool = Field(
        default=False,
        description="Whether to include expired long-term memory items",
    )
    now: Optional[datetime] = Field(default=None, description="Reference time for expiry filtering")
