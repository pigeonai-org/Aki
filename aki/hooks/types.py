"""
Hook Event Types

Defines the event types, event payloads, and hook results for the lifecycle hook system.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """All supported hook event types."""

    # Session lifecycle
    SESSION_START = "session_start"
    SESSION_END = "session_end"

    # Tool execution
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"

    # Permission
    PERMISSION_REQUEST = "permission_request"

    # Agent lifecycle
    AGENT_SPAWN = "agent_spawn"
    AGENT_COMPLETE = "agent_complete"

    # Context management
    CONTEXT_COMPACTION = "context_compaction"

    # Resilience
    MODEL_FAILOVER = "model_failover"
    ERROR_RECOVERY = "error_recovery"

    # Communication
    MESSAGE_SEND = "message_send"
    MESSAGE_RECEIVE = "message_receive"


class HookEvent(BaseModel):
    """Payload delivered to hook handlers when an event fires."""

    event_type: EventType
    agent_id: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)
    data: dict[str, Any] = Field(default_factory=dict)


class HookResult(BaseModel):
    """
    Result returned by a hook handler.

    Handlers can:
    - Block the operation by setting allow=False
    - Modify the operation data via modified_data
    - Attach a human-readable message
    """

    allow: bool = True
    modified_data: Optional[dict[str, Any]] = None
    message: str = ""
