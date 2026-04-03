"""
Rate Limit Backoff

Exponential backoff with jitter for rate-limited API requests.
"""

import asyncio
import logging
import random
from typing import Any, Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RateLimitBackoff:
    """
    Retries an async operation with exponential backoff and jitter.

    Usage::

        backoff = RateLimitBackoff(base_delay=1.0, max_delay=60.0, max_retries=5)
        result = await backoff.execute_with_retry(llm.chat, messages, tools=tools)
    """

    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        max_retries: int = 5,
        jitter: float = 0.5,
    ) -> None:
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.jitter = jitter

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for the given attempt number with jitter."""
        delay = min(self.base_delay * (2**attempt), self.max_delay)
        jitter_range = delay * self.jitter
        return delay + random.uniform(-jitter_range, jitter_range)

    async def execute_with_retry(
        self,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
        **kwargs: Any,
    ) -> T:
        """
        Execute an async function with retry logic.

        Args:
            func: The async callable to execute.
            *args: Positional arguments for func.
            retryable_exceptions: Tuple of exception types to retry on.
            **kwargs: Keyword arguments for func.

        Returns:
            The result of func.

        Raises:
            The last exception if all retries are exhausted.
        """
        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except retryable_exceptions as e:
                last_exception = e
                if attempt >= self.max_retries:
                    break

                delay = self._calculate_delay(attempt)
                logger.warning(
                    "Attempt %d/%d failed (%s: %s). Retrying in %.1fs...",
                    attempt + 1,
                    self.max_retries + 1,
                    type(e).__name__,
                    str(e)[:200],
                    delay,
                )
                await asyncio.sleep(delay)

        raise last_exception  # type: ignore[misc]
