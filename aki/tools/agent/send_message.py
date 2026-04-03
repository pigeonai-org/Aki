"""
Tool: send_agent_message

Allows an agent to send a message to another agent via the AgentBus.
"""

from typing import Any

from aki.agent.communication.messages import AgentMessage
from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.registry import ToolRegistry


@ToolRegistry.register
class SendAgentMessageTool(BaseTool):
    """Send a message to another agent on the bus."""

    name: str = "send_agent_message"
    description: str = (
        "Send a message to another agent by address (e.g. 'task:Localizer'). "
        "The recipient must be registered on the bus."
    )
    parameters: list[ToolParameter] = [
        ToolParameter(
            name="recipient",
            type="string",
            description="Recipient address (agent_id or pattern like 'task:Localizer').",
            required=True,
        ),
        ToolParameter(
            name="content",
            type="string",
            description="Message content.",
            required=True,
        ),
    ]

    def __init__(self, bus: Any = None, agent_id: str = "") -> None:
        super().__init__()
        self.bus = bus
        self.sender_agent_id = agent_id

    async def execute(self, **kwargs: Any) -> ToolResult:
        recipient = str(kwargs.get("recipient", "")).strip()
        content = str(kwargs.get("content", "")).strip()

        if not recipient or not content:
            return ToolResult.fail("Both 'recipient' and 'content' are required.")

        if self.bus is None:
            return ToolResult.fail("AgentBus not configured — cannot send messages.")

        msg = AgentMessage(
            sender=self.sender_agent_id,
            recipient=recipient,
            content=content,
        )
        delivered = await self.bus.send(msg)

        if delivered == 0:
            return ToolResult.fail(f"No agents matched recipient '{recipient}'.")

        return ToolResult.ok(data={"delivered_to": delivered, "message_id": msg.id})
