"""
Memory module - Layered memory system.

Architecture:
    Layer 0: Working Memory  — context window (managed externally by context manager)
    Layer 1: Session Memory  — persistent per-session message & observation log
    Layer 2: Long-term Memory — 5 dimensions (user, episodic, semantic, procedural, persona)
    Layer 3: Core Memory     — personality definition (managed externally by persona loader)

Legacy short-term / long-term stores are still available via MemoryManager for
backward compatibility. New code should use AkiMemorySystem.
"""

from aki.memory.base import MemoryItem, MemoryStore, MemoryStrategy
from aki.memory.manager import (
    AkiMemorySystem,
    MemoryManager,
    get_aki_memory,
    get_memory_manager,
    reset_aki_memory,
    reset_memory_manager,
)
from aki.memory.migration import migrate_legacy_json_to_long_term
from aki.memory.recall import RecallPipeline, RecallResult
from aki.memory.review import MemoryReviewer, ReviewResult
from aki.memory.session import Session, SessionMeta, SessionStore
from aki.memory.stores.long_term import LongTermMemoryStore
from aki.memory.stores.short_term import ShortTermMemoryStore
from aki.memory.strategies.sliding_window import SlidingWindowStrategy
from aki.memory.types import MemoryCategory, MemoryDimension, MemoryQuery, MemoryScope, SessionState

__all__ = [
    # Base
    "MemoryItem",
    "MemoryStore",
    "MemoryStrategy",
    "MemoryScope",
    "MemoryCategory",
    "MemoryQuery",
    # Stores
    "ShortTermMemoryStore",
    "LongTermMemoryStore",
    # Strategies
    "SlidingWindowStrategy",
    # Manager (legacy)
    "MemoryManager",
    "get_memory_manager",
    "reset_memory_manager",
    "migrate_legacy_json_to_long_term",
    # New layered system
    "AkiMemorySystem",
    "get_aki_memory",
    "reset_aki_memory",
    "MemoryDimension",
    "SessionState",
    # Session
    "SessionStore",
    "Session",
    "SessionMeta",
    # Recall & Review
    "RecallPipeline",
    "RecallResult",
    "MemoryReviewer",
    "ReviewResult",
]
