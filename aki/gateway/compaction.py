"""Context compaction for long-running conversations.

When conversation_history grows too large for the model's context window,
older messages are summarized into a single ``[Conversation summary]``
system message.  Recent messages are kept intact.

The memory flush step is handled by ``SessionManager._memory_review()``
which already runs after every turn — no additional action needed here.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from aki.models.types.llm import LLMInterface

logger = logging.getLogger(__name__)

# Conservative characters-per-token estimate (no tokenizer dependency).
_CHARS_PER_TOKEN = 4


class ContextCompactor:
    """Summarises old conversation history to stay within context limits."""

    def __init__(
        self,
        llm: LLMInterface,
        max_context_tokens: int = 8000,
        soft_threshold_ratio: float = 0.80,
        keep_recent: int = 10,
    ) -> None:
        self._llm = llm
        self._max_tokens = max_context_tokens
        self._soft_tokens = int(max_context_tokens * soft_threshold_ratio)
        self._keep_recent = keep_recent

    # ------------------------------------------------------------------
    # Token estimation
    # ------------------------------------------------------------------

    @staticmethod
    def estimate_tokens(history: list[dict[str, Any]]) -> int:
        """Cheap token count approximation (characters / 4)."""
        total_chars = sum(len(str(m.get("content", ""))) for m in history)
        return total_chars // _CHARS_PER_TOKEN

    def needs_compaction(self, history: list[dict[str, Any]]) -> bool:
        """Return ``True`` if history exceeds the soft threshold."""
        return self.estimate_tokens(history) >= self._soft_tokens

    # ------------------------------------------------------------------
    # Compaction
    # ------------------------------------------------------------------

    async def compact(
        self,
        history: list[dict[str, Any]],
        persistence: Any | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Compact *history* by summarising older messages.

        Returns a new (shorter) history list.  If *persistence* and
        *session_id* are provided, a ``compaction`` entry is appended to
        the JSONL transcript.
        """
        if not self.needs_compaction(history):
            return history

        # Not enough messages to meaningfully compact
        if len(history) <= self._keep_recent + 2:
            return history

        old_messages = history[: -self._keep_recent]
        recent_messages = history[-self._keep_recent :]

        # Build text block from old messages
        lines: list[str] = []
        for m in old_messages:
            role = m.get("role", "?")
            content = m.get("content", "")
            lines.append(f"[{role}]: {content}")
        old_text = "\n".join(lines)

        # Ask the LLM to summarise
        try:
            response = await self._llm.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Summarize the following conversation history into a concise "
                            "paragraph.  Preserve key facts, decisions, user preferences, "
                            "and action outcomes.  Do not add commentary.  Output only the "
                            "summary."
                        ),
                    },
                    {"role": "user", "content": old_text},
                ],
                temperature=0.3,
                max_tokens=500,
            )
            summary_text = str(response.content)
        except Exception as exc:
            logger.warning("Compaction LLM call failed (%s); skipping compaction", exc)
            return history

        # Record compaction in JSONL (if persistence is available)
        if persistence is not None and session_id is not None:
            persistence.append_entry(session_id, {
                "id": str(uuid4()),
                "type": "compaction",
                "ts": datetime.now(timezone.utc).isoformat(),
                "summary": summary_text,
                "replaced_count": len(old_messages),
            })

        # Return compacted history
        compacted: list[dict[str, Any]] = [
            {"role": "system", "content": f"[Conversation summary]: {summary_text}"},
        ]
        compacted.extend(recent_messages)

        logger.info(
            "Compacted %d old messages into summary (%d → %d entries)",
            len(old_messages),
            len(history),
            len(compacted),
        )
        return compacted
