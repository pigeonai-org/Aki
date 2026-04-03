"""
Hook Engine

Central event dispatch system for lifecycle hooks.
Handlers are registered per EventType and fire in priority order.
"""

import logging
from collections import defaultdict
from typing import Awaitable, Callable

from aki.hooks.types import EventType, HookEvent, HookResult

logger = logging.getLogger(__name__)

HookHandler = Callable[[HookEvent], Awaitable[HookResult]]


class _RegisteredHandler:
    """Internal wrapper tracking handler priority."""

    __slots__ = ("handler", "priority")

    def __init__(self, handler: HookHandler, priority: int) -> None:
        self.handler = handler
        self.priority = priority


class HookEngine:
    """
    Central event dispatch for lifecycle hooks.

    Handlers are registered per EventType and fire in ascending priority order.
    Lower priority numbers execute first.

    Usage::

        engine = HookEngine()

        async def my_hook(event: HookEvent) -> HookResult:
            print(f"Tool {event.data['tool_name']} was called")
            return HookResult()

        engine.register(EventType.PRE_TOOL_USE, my_hook, priority=10)
        result = await engine.fire(HookEvent(event_type=EventType.PRE_TOOL_USE, data={...}))
    """

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[_RegisteredHandler]] = defaultdict(list)

    def register(
        self,
        event_type: EventType,
        handler: HookHandler,
        priority: int = 0,
    ) -> None:
        """
        Register a hook handler for an event type.

        Args:
            event_type: The event to listen for.
            handler: Async callable receiving HookEvent, returning HookResult.
            priority: Execution order (lower runs first). Default 0.
        """
        entry = _RegisteredHandler(handler, priority)
        handlers = self._handlers[event_type]
        handlers.append(entry)
        handlers.sort(key=lambda h: h.priority)

    def unregister(self, event_type: EventType, handler: HookHandler) -> None:
        """Remove a previously registered handler."""
        handlers = self._handlers.get(event_type, [])
        self._handlers[event_type] = [h for h in handlers if h.handler is not handler]

    async def fire(self, event: HookEvent) -> HookResult:
        """
        Fire an event and return the merged result.

        Handlers execute in priority order. If any handler sets ``allow=False``,
        the merged result will have ``allow=False`` and execution stops early.
        The last non-None ``modified_data`` wins.

        Returns HookResult(allow=True) immediately when no handlers are registered
        (zero overhead in the common case).
        """
        handlers = self._handlers.get(event.event_type)
        if not handlers:
            return HookResult()

        merged = HookResult()
        for entry in handlers:
            try:
                result = await entry.handler(event)
            except Exception:
                logger.exception("Hook handler %s failed for %s", entry.handler, event.event_type)
                # For permission-check events, default to deny on error instead of silently continuing
                if event.event_type == EventType.PRE_TOOL_USE:
                    return HookResult(allow=False, message="Hook handler error — action denied for safety")
                continue

            if not result.allow:
                return HookResult(allow=False, message=result.message, modified_data=result.modified_data)

            if result.modified_data is not None:
                merged.modified_data = result.modified_data
            if result.message:
                merged.message = result.message

        return merged

    async def fire_all(self, event: HookEvent) -> list[HookResult]:
        """
        Fire an event and collect results from all handlers (no early stopping).

        Useful for notification-style events where every handler should run.
        """
        handlers = self._handlers.get(event.event_type)
        if not handlers:
            return []

        results: list[HookResult] = []
        for entry in handlers:
            try:
                result = await entry.handler(event)
                results.append(result)
            except Exception:
                logger.exception("Hook handler %s failed for %s", entry.handler, event.event_type)
        return results

    def has_handlers(self, event_type: EventType) -> bool:
        """Check if any handlers are registered for an event type."""
        return bool(self._handlers.get(event_type))

    def clear(self, event_type: EventType | None = None) -> None:
        """
        Remove all handlers.

        Args:
            event_type: If provided, only clear handlers for this event type.
                        If None, clear all handlers.
        """
        if event_type is None:
            self._handlers.clear()
        else:
            self._handlers.pop(event_type, None)
