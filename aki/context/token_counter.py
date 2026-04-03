"""
Token Counter

Estimates token counts for messages using tiktoken (if available) or a heuristic fallback.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Try to use tiktoken for accurate counts; fall back to heuristic
_encoder = None
try:
    import tiktoken

    _encoder = tiktoken.get_encoding("cl100k_base")
except Exception:
    logger.debug("tiktoken not available, using heuristic token estimation")


def _heuristic_count(text: str) -> int:
    """Rough estimate: ~4 characters per token for English, ~2 for CJK-heavy text."""
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff" or "\u3000" <= c <= "\u303f")
    if cjk > len(text) * 0.3:
        return max(1, len(text) // 2)
    return max(1, len(text) // 4)


class TokenCounter:
    """
    Counts tokens in text or message lists.

    Uses tiktoken when available, otherwise falls back to a character-based heuristic.
    """

    def count_text(self, text: str) -> int:
        """Count tokens in a plain text string."""
        if not text:
            return 0
        if _encoder is not None:
            return len(_encoder.encode(text))
        return _heuristic_count(text)

    def count_message(self, message: dict[str, Any]) -> int:
        """
        Count tokens in a single chat message.

        Accounts for role overhead (~4 tokens) and content.
        """
        overhead = 4  # role, separators
        content = message.get("content", "")
        if isinstance(content, str):
            return overhead + self.count_text(content)
        if isinstance(content, list):
            # Multi-part content (text blocks, tool results, etc.)
            total = overhead
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text", "") or str(part.get("content", ""))
                    total += self.count_text(text)
                elif isinstance(part, str):
                    total += self.count_text(part)
            return total
        return overhead + self.count_text(str(content))

    def count_messages(self, messages: list[dict[str, Any]]) -> int:
        """Count total tokens across a list of messages."""
        return sum(self.count_message(m) for m in messages)
