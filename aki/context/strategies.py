"""
Compaction Strategies

Pluggable strategies for reducing conversation context size when approaching token limits.
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from aki.context.budget import TokenBudget

logger = logging.getLogger(__name__)


class CompactionStrategy(ABC):
    """Base class for context compaction strategies."""

    name: str = "base"

    @abstractmethod
    async def compact(
        self,
        messages: list[dict[str, Any]],
        budget: TokenBudget,
        llm: Optional[Any] = None,
    ) -> list[dict[str, Any]]:
        """
        Compact messages to fit within budget.

        Args:
            messages: Current conversation messages.
            budget: Token budget with capacity info.
            llm: Optional LLM interface (needed by summarize strategy).

        Returns:
            Compacted message list.
        """
        ...


class TruncateStrategy(CompactionStrategy):
    """
    Drop the oldest messages, keeping the most recent ones.

    Always preserves the system message (index 0) and at least ``keep_recent``
    messages from the tail.
    """

    name = "truncate"

    def __init__(self, keep_recent: int = 10) -> None:
        self.keep_recent = keep_recent

    async def compact(
        self,
        messages: list[dict[str, Any]],
        budget: TokenBudget,
        llm: Optional[Any] = None,
    ) -> list[dict[str, Any]]:
        if len(messages) <= self.keep_recent + 1:
            return messages

        # Keep system message (if present) + last N messages
        system_msgs = [m for m in messages[:1] if m.get("role") == "system"]
        tail = messages[-self.keep_recent :]
        compacted = system_msgs + tail

        logger.info(
            "TruncateStrategy: %d -> %d messages (kept %d recent)",
            len(messages),
            len(compacted),
            self.keep_recent,
        )
        return compacted


class StripMediaStrategy(CompactionStrategy):
    """
    Replace large tool results with compact summaries.

    Scans for tool result messages whose content exceeds ``max_result_chars``
    and replaces them with a truncated preview.
    """

    name = "strip_media"

    def __init__(self, max_result_chars: int = 2000) -> None:
        self.max_result_chars = max_result_chars

    async def compact(
        self,
        messages: list[dict[str, Any]],
        budget: TokenBudget,
        llm: Optional[Any] = None,
    ) -> list[dict[str, Any]]:
        compacted: list[dict[str, Any]] = []
        stripped_count = 0

        for msg in messages:
            if msg.get("role") == "tool":
                content = msg.get("content", "")
                content_str = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                if len(content_str) > self.max_result_chars:
                    preview = content_str[: self.max_result_chars]
                    compacted.append({
                        **msg,
                        "content": f"[Truncated result - {len(content_str)} chars]\n{preview}...",
                    })
                    stripped_count += 1
                    continue
            compacted.append(msg)

        if stripped_count:
            logger.info("StripMediaStrategy: truncated %d large tool results", stripped_count)
        return compacted


class SummarizeOldStrategy(CompactionStrategy):
    """
    Use the LLM to summarize older messages into a concise synopsis.

    Keeps the system message and recent messages intact, replaces everything
    in between with an LLM-generated summary.
    """

    name = "summarize_old"

    def __init__(self, keep_recent: int = 6) -> None:
        self.keep_recent = keep_recent

    async def compact(
        self,
        messages: list[dict[str, Any]],
        budget: TokenBudget,
        llm: Optional[Any] = None,
    ) -> list[dict[str, Any]]:
        if llm is None:
            logger.warning("SummarizeOldStrategy: no LLM provided, falling back to truncation")
            fallback = TruncateStrategy(keep_recent=self.keep_recent)
            return await fallback.compact(messages, budget)

        if len(messages) <= self.keep_recent + 2:
            return messages

        # Split: [system] + [old messages to summarize] + [recent messages to keep]
        system_msgs = [m for m in messages[:1] if m.get("role") == "system"]
        start_idx = len(system_msgs)
        old_messages = messages[start_idx : -self.keep_recent]
        recent_messages = messages[-self.keep_recent :]

        if not old_messages:
            return messages

        # Build summary request
        old_text = _format_messages_for_summary(old_messages)
        summary_prompt = [
            {
                "role": "system",
                "content": (
                    "Summarize the following conversation excerpt into a concise synopsis. "
                    "Preserve key facts, decisions, tool outputs, and context needed for the "
                    "conversation to continue. Use bullet points. Be brief."
                ),
            },
            {"role": "user", "content": old_text},
        ]

        try:
            response = await llm.chat(summary_prompt, max_tokens=1024)
            summary_text = response.content if isinstance(response.content, str) else str(response.content)
        except Exception:
            logger.exception("SummarizeOldStrategy: LLM summarization failed, falling back to truncation")
            fallback = TruncateStrategy(keep_recent=self.keep_recent)
            return await fallback.compact(messages, budget)

        summary_message = {
            "role": "user",
            "content": f"[Conversation summary - {len(old_messages)} messages compacted]\n{summary_text}",
        }

        compacted = system_msgs + [summary_message] + recent_messages
        logger.info(
            "SummarizeOldStrategy: %d -> %d messages (summarized %d old messages)",
            len(messages),
            len(compacted),
            len(old_messages),
        )
        return compacted


def _format_messages_for_summary(messages: list[dict[str, Any]]) -> str:
    """Format messages into readable text for the summarizer."""
    lines: list[str] = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                p.get("text", "") if isinstance(p, dict) else str(p) for p in content
            )
        # Truncate very long individual messages
        if len(str(content)) > 1500:
            content = str(content)[:1500] + "..."
        lines.append(f"[{role}]: {content}")
    return "\n".join(lines)
