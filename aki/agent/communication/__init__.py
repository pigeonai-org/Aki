"""
Agent Communication

Peer-to-peer messaging, event broadcasting, and pipeline-style addressing
for inter-agent coordination.
"""

from aki.agent.communication.addressing import AgentAddress
from aki.agent.communication.bus import AgentBus
from aki.agent.communication.messages import AgentEvent, AgentMessage

__all__ = [
    "AgentAddress",
    "AgentBus",
    "AgentEvent",
    "AgentMessage",
]
