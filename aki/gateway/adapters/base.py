"""Abstract base class for platform adapters.

Each messaging platform (Discord, Telegram, Slack, …) gets its own
adapter that normalises platform-specific events into
:class:`InboundMessage` and delivers :class:`OutboundMessage` back.

The adapter does **not** need to know about the Gateway internals — it
receives a callback (``on_message``) and uses it to process each
inbound message.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Awaitable, Callable

from aki.gateway.types import InboundMessage, OutboundMessage, PlatformContext


class PlatformAdapter(ABC):
    """Abstract base for messaging platform integrations."""

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Unique platform identifier, e.g. ``'discord'``, ``'telegram'``."""

    @abstractmethod
    async def start(
        self,
        on_message: Callable[[InboundMessage], Awaitable[OutboundMessage]],
    ) -> None:
        """Start listening for messages.

        The adapter must call *on_message* for each inbound message it
        receives and deliver the returned ``OutboundMessage`` back to the
        platform (typically via :meth:`send_reply`).
        """

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully disconnect from the platform."""

    @abstractmethod
    async def send_typing(self, ctx: PlatformContext) -> None:
        """Send a typing / "agent is thinking" indicator."""

    @abstractmethod
    async def send_reply(self, msg: OutboundMessage) -> None:
        """Deliver a reply message to the platform."""
