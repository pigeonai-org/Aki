"""
Error Recovery Handler

Circuit-breaker style error recovery for the agent execution loop.
Maps exception types to recovery actions.
"""

import logging
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class RecoveryAction(str, Enum):
    """Actions the agent loop can take in response to an error."""

    COMPACT = "compact"  # Compact context and retry
    RETRY_BACKOFF = "retry_backoff"  # Retry with exponential backoff
    FAILOVER = "failover"  # Switch to next model provider
    CONTINUE = "continue"  # Ignore error and continue (partial result)
    ABORT = "abort"  # Stop the agent loop


class RecoveryResult:
    """Recovery decision with optional context."""

    __slots__ = ("action", "message", "data")

    def __init__(self, action: RecoveryAction, message: str = "", data: Any = None) -> None:
        self.action = action
        self.message = message
        self.data = data


class ErrorRecoveryHandler:
    """
    Maps exceptions to recovery actions for the agent loop.

    The agent loop wraps its LLM calls in try/except and delegates to
    this handler to decide what to do next.

    Usage::

        handler = ErrorRecoveryHandler(context_manager=ctx_mgr)
        try:
            response = await llm.chat(messages, tools=tools)
        except Exception as e:
            result = handler.handle_error(e, messages)
            if result.action == RecoveryAction.COMPACT:
                messages = await ctx_mgr.compact(messages, llm)
            elif result.action == RecoveryAction.ABORT:
                break
    """

    def __init__(
        self,
        context_manager: Optional[Any] = None,
        failover: Optional[Any] = None,
        max_consecutive_errors: int = 3,
    ) -> None:
        self._context_manager = context_manager
        self._failover = failover
        self._max_consecutive_errors = max_consecutive_errors
        self._consecutive_errors = 0

    def handle_error(
        self,
        error: Exception,
        messages: list[dict[str, Any]] | None = None,
    ) -> RecoveryResult:
        """
        Determine recovery action for an error.

        Args:
            error: The exception that occurred.
            messages: Current message list (for context-aware decisions).

        Returns:
            RecoveryResult with the recommended action.
        """
        self._consecutive_errors += 1
        error_name = type(error).__name__
        error_msg = str(error)[:300]

        # Circuit breaker
        if self._consecutive_errors >= self._max_consecutive_errors:
            logger.error(
                "Circuit breaker: %d consecutive errors, aborting. Last: %s",
                self._consecutive_errors,
                error_msg,
            )
            return RecoveryResult(
                RecoveryAction.ABORT,
                f"Too many consecutive errors ({self._consecutive_errors}). Last: {error_name}",
            )

        # Prompt/context too long
        if _is_context_too_long(error):
            if self._context_manager is not None:
                logger.info("Context too long, recommending compaction")
                return RecoveryResult(RecoveryAction.COMPACT, "Context window exceeded, compacting")
            return RecoveryResult(RecoveryAction.ABORT, "Context too long and no context manager available")

        # Rate limit
        if _is_rate_limit(error):
            logger.info("Rate limited, recommending backoff retry")
            return RecoveryResult(RecoveryAction.RETRY_BACKOFF, f"Rate limited: {error_msg}")

        # Provider/connection error
        if _is_provider_error(error):
            if self._failover is not None:
                logger.info("Provider error, recommending failover")
                return RecoveryResult(RecoveryAction.FAILOVER, f"Provider error: {error_msg}")
            return RecoveryResult(RecoveryAction.RETRY_BACKOFF, f"Provider error (no failover): {error_msg}")

        # Max tokens exceeded
        if _is_max_tokens(error):
            return RecoveryResult(RecoveryAction.CONTINUE, "Max output tokens reached, using partial response")

        # Unknown error
        logger.warning("Unknown error type %s: %s", error_name, error_msg)
        return RecoveryResult(RecoveryAction.ABORT, f"Unrecoverable error: {error_name}: {error_msg}")

    def record_success(self) -> None:
        """Record a successful operation (resets the consecutive error counter)."""
        self._consecutive_errors = 0


def _is_context_too_long(error: Exception) -> bool:
    """Check if the error indicates the context window was exceeded."""
    msg = str(error).lower()
    return any(
        keyword in msg
        for keyword in ("prompt is too long", "context_length_exceeded", "maximum context length", "token limit")
    )


def _is_rate_limit(error: Exception) -> bool:
    """Check if the error is a rate limit."""
    msg = str(error).lower()
    return any(keyword in msg for keyword in ("rate_limit", "rate limit", "429", "too many requests"))


def _is_provider_error(error: Exception) -> bool:
    """Check if the error is a provider/connection issue."""
    msg = str(error).lower()
    return any(
        keyword in msg
        for keyword in (
            "connection",
            "timeout",
            "502",
            "503",
            "service unavailable",
            "internal server error",
            "500",
        )
    )


def _is_max_tokens(error: Exception) -> bool:
    """Check if the error indicates max output tokens was reached."""
    msg = str(error).lower()
    if "max_tokens" in msg:
        return True
    if "maximum" in msg and "tokens" in msg:
        return True
    if "output" in msg and "length" in msg:
        return True
    return False
