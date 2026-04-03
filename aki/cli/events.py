"""
UI Event System

Broadcast event bus: every subscriber gets every event.
Uses per-subscriber asyncio.Queue for lock-free fan-out.
"""

import asyncio
import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class UIEventType(str, Enum):
    """All UI event types flowing through the event bus."""

    USER_INPUT = "user_input"
    AGENT_THINKING = "agent_thinking"
    AGENT_REPLY = "agent_reply"
    AGENT_SPAWN = "agent_spawn"
    AGENT_COMPLETE = "agent_complete"
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    BTW_REPLY = "btw_reply"
    CANCEL = "cancel"
    ERROR = "error"


class UIEvent(BaseModel):
    """Single event flowing through the UI event bus."""

    type: UIEventType
    agent_id: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.monotonic)

    model_config = {"arbitrary_types_allowed": True}


class UIEventSubscriber:
    """A single subscriber's event queue."""

    def __init__(self, maxsize: int = 1000) -> None:
        self._queue: asyncio.Queue[UIEvent] = asyncio.Queue(maxsize=maxsize)

    def put(self, event: UIEvent) -> None:
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            pass

    async def next(self, timeout: float = 0.25) -> UIEvent | None:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            return None

    @property
    def pending(self) -> int:
        return self._queue.qsize()


class UIEventBus:
    """Broadcast event bus — every event is delivered to every subscriber.

    Usage::

        bus = UIEventBus()
        dispatch_sub = bus.subscribe()   # for dispatch loop
        renderer_sub = bus.subscribe()   # for renderer

        bus.emit_nowait(UIEvent(type=UIEventType.USER_INPUT, data={"text": "hi"}))

        # Both subscribers receive the event:
        event1 = await dispatch_sub.next()
        event2 = await renderer_sub.next()
    """

    def __init__(self) -> None:
        self._subscribers: list[UIEventSubscriber] = []
        self._closed = False

    def subscribe(self) -> UIEventSubscriber:
        """Create a new subscriber that receives all future events."""
        sub = UIEventSubscriber()
        self._subscribers.append(sub)
        return sub

    async def emit(self, event: UIEvent) -> None:
        """Async broadcast to all subscribers."""
        if not self._closed:
            for sub in self._subscribers:
                sub.put(event)

    def emit_nowait(self, event: UIEvent) -> None:
        """Non-blocking broadcast (for signal handlers, threads)."""
        if not self._closed:
            for sub in self._subscribers:
                sub.put(event)

    def close(self) -> None:
        self._closed = True
