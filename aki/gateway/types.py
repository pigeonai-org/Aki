"""Unified message types for the Gateway layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass
class PlatformContext:
    """Opaque platform metadata carried alongside a message."""

    platform: str  # "discord", "telegram", "rest", "cli"
    channel_id: str  # Platform-specific channel / DM identifier
    user_id: str  # Platform-specific user identifier
    user_display_name: str = ""
    raw_event: Any = None  # Original platform event (for reply routing)


@dataclass
class InboundMessage:
    """Platform-agnostic normalized message entering the system."""

    text: str
    platform_ctx: PlatformContext
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    message_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass
class OutboundMessage:
    """Reply produced by the Gateway, ready for platform delivery."""

    text: str
    session_id: str
    platform_ctx: PlatformContext
    in_reply_to: str  # message_id of the InboundMessage
