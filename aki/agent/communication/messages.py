"""
Agent Message Types

Defines the message and event types used for inter-agent communication.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class AgentMessage(BaseModel):
    """
    Peer-to-peer message between agents.

    Supports request/response pairing via correlation_id.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    sender: str = Field(..., description="Sender agent_id or address")
    recipient: str = Field(..., description="Recipient agent_id or address pattern (e.g. 'task:Localizer')")
    content: Any = Field(default=None, description="Message payload")
    message_type: str = Field(
        default="request",
        description="Message type: 'request', 'response', 'event', 'broadcast'",
    )
    correlation_id: Optional[str] = Field(
        default=None,
        description="Links a response to its original request",
    )
    timestamp: datetime = Field(default_factory=datetime.now)

    def create_response(self, content: Any) -> "AgentMessage":
        """Create a response message to this request."""
        return AgentMessage(
            sender=self.recipient,
            recipient=self.sender,
            content=content,
            message_type="response",
            correlation_id=self.id,
        )


class AgentEvent(BaseModel):
    """
    Broadcast event for coordination.

    Published to all agents subscribed to the event_name.
    """

    source: str = Field(..., description="Source agent_id")
    event_name: str = Field(..., description="Event identifier (e.g. 'transcription_complete')")
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)
