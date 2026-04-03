"""
Sliding Window Memory Strategy

Simple strategy that keeps the N most recent memories.
"""

from aki.memory.base import MemoryItem, MemoryStrategy


class SlidingWindowStrategy(MemoryStrategy):
    """
    Sliding window memory strategy.

    Keeps the most recent memories up to a window size.
    Simple but effective for short-term memory management.
    """

    def __init__(self, window_size: int = 20):
        """
        Initialize the strategy.

        Args:
            window_size: Maximum number of memories to keep
        """
        self.window_size = window_size

    def select(
        self,
        memories: list[MemoryItem],
        limit: int,
    ) -> list[MemoryItem]:
        """
        Select the most recent memories.

        Args:
            memories: All available memories
            limit: Maximum number to return (overrides window_size if smaller)

        Returns:
            Most recent memories up to the limit
        """
        # Sort by timestamp descending
        sorted_memories = sorted(
            memories,
            key=lambda m: m.timestamp,
            reverse=True,
        )

        # Take the minimum of limit and window_size
        actual_limit = min(limit, self.window_size)

        return sorted_memories[:actual_limit]
