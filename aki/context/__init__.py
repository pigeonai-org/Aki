"""
Context Management

Token budget tracking, automatic context compaction, and message management.
"""

from aki.context.budget import TokenBudget
from aki.context.manager import ContextManager
from aki.context.strategies import (
    CompactionStrategy,
    StripMediaStrategy,
    SummarizeOldStrategy,
    TruncateStrategy,
)
from aki.context.token_counter import TokenCounter

__all__ = [
    "CompactionStrategy",
    "ContextManager",
    "StripMediaStrategy",
    "SummarizeOldStrategy",
    "TokenBudget",
    "TokenCounter",
    "TruncateStrategy",
]
