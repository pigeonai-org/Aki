"""
Context Manager

Manages token budget and automatic compaction for agent conversations.
Replaces the hardcoded 20-iteration cap with intelligent context management.
"""

import logging
from typing import Any, Optional

from aki.context.budget import TokenBudget
from aki.context.strategies import (
    CompactionStrategy,
    StripMediaStrategy,
    SummarizeOldStrategy,
    TruncateStrategy,
)
from aki.context.token_counter import TokenCounter

logger = logging.getLogger(__name__)

# Default compaction strategy chain
_DEFAULT_STRATEGIES: list[CompactionStrategy] = [
    StripMediaStrategy(max_result_chars=2000),
    SummarizeOldStrategy(keep_recent=6),
    TruncateStrategy(keep_recent=10),
]


class ContextManager:
    """
    Manages token budget for agent conversations.

    Tracks token usage, detects when compaction is needed, and applies
    a chain of compaction strategies to keep the context within limits.

    Usage::

        ctx = ContextManager(max_context_tokens=128_000)
        budget = ctx.allocate_budget(system_prompt_tokens=2000, tool_schemas_tokens=1500)

        # During agent loop:
        if ctx.needs_compaction(messages):
            messages = await ctx.compact(messages, llm)
    """

    def __init__(
        self,
        max_context_tokens: int = 128_000,
        strategies: list[CompactionStrategy] | None = None,
        token_counter: TokenCounter | None = None,
        max_compaction_failures: int = 3,
    ) -> None:
        self.max_context_tokens = max_context_tokens
        self.strategies = strategies or list(_DEFAULT_STRATEGIES)
        self.token_counter = token_counter or TokenCounter()
        self._compaction_failures = 0
        self._max_compaction_failures = max_compaction_failures

    def estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Estimate total tokens for a list of messages."""
        return self.token_counter.count_messages(messages)

    def allocate_budget(
        self,
        system_prompt_tokens: int = 0,
        tool_schemas_tokens: int = 0,
        reserve_tokens: int = 4_000,
    ) -> TokenBudget:
        """
        Create a token budget for this conversation.

        Args:
            system_prompt_tokens: Tokens consumed by the system prompt.
            tool_schemas_tokens: Tokens consumed by tool definitions.
            reserve_tokens: Buffer reserved for model output.

        Returns:
            TokenBudget tracking capacity and usage.
        """
        return TokenBudget(
            max_context_tokens=self.max_context_tokens,
            system_prompt_tokens=system_prompt_tokens,
            tool_schemas_tokens=tool_schemas_tokens,
            reserve_tokens=reserve_tokens,
        )

    def needs_compaction(self, messages: list[dict[str, Any]], budget: Optional[TokenBudget] = None) -> bool:
        """
        Check if the message list needs compaction.

        Uses the budget's compaction threshold if provided, otherwise uses
        75% of max_context_tokens as the threshold.
        """
        if self._compaction_failures >= self._max_compaction_failures:
            logger.warning("Compaction circuit breaker tripped (%d consecutive failures)", self._compaction_failures)
            return False

        token_count = self.estimate_tokens(messages)
        if budget is not None:
            return token_count >= budget.compaction_threshold
        return token_count >= int(self.max_context_tokens * 0.75)

    async def compact(
        self,
        messages: list[dict[str, Any]],
        llm: Optional[Any] = None,
        budget: Optional[TokenBudget] = None,
    ) -> list[dict[str, Any]]:
        """
        Apply compaction strategies in chain until context fits.

        Strategies are tried in order. After each strategy, token count
        is re-evaluated. Stops as soon as the context fits within budget.

        Args:
            messages: Current conversation messages.
            llm: Optional LLM for summarization strategy.
            budget: Optional budget for threshold calculation.

        Returns:
            Compacted message list.
        """
        threshold = budget.compaction_threshold if budget else int(self.max_context_tokens * 0.75)
        current = messages
        initial_tokens = self.estimate_tokens(current)

        for strategy in self.strategies:
            try:
                current = await strategy.compact(current, budget or TokenBudget(), llm)
            except Exception:
                logger.exception("Compaction strategy %s failed", strategy.name)
                continue

            token_count = self.estimate_tokens(current)
            logger.info(
                "After %s: %d -> %d tokens",
                strategy.name,
                initial_tokens,
                token_count,
            )
            if token_count < threshold:
                self._compaction_failures = 0
                if budget is not None:
                    budget.update_message_tokens(token_count)
                return current

        # None of the strategies brought us under threshold
        self._compaction_failures += 1
        final_tokens = self.estimate_tokens(current)
        logger.warning(
            "Compaction did not reach threshold (%d tokens remaining, threshold %d, failure %d/%d)",
            final_tokens,
            threshold,
            self._compaction_failures,
            self._max_compaction_failures,
        )
        if budget is not None:
            budget.update_message_tokens(final_tokens)
        return current

    def reset_circuit_breaker(self) -> None:
        """Reset the compaction failure counter."""
        self._compaction_failures = 0
