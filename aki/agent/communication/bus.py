"""
Agent Bus

Central message bus for agent-to-agent communication.
Supports direct messaging, address-pattern routing, and broadcast events.
"""

import asyncio
import logging
from collections import defaultdict
from typing import Callable, Optional

from aki.agent.communication.addressing import AgentAddress
from aki.agent.communication.messages import AgentEvent, AgentMessage

logger = logging.getLogger(__name__)


class AgentBus:
    """
    Central message bus for inter-agent communication.

    Supports:
    - Direct messaging (agent_id -> agent_id)
    - Address-pattern routing (project:role -> matching agents)
    - Broadcast events to subscribers
    - Async mailbox per agent with timeout-based receive

    Usage::

        bus = AgentBus()
        bus.register_agent("agent-1", "translation:MediaExtractor")
        bus.register_agent("agent-2", "translation:Localizer")

        await bus.send(AgentMessage(sender="agent-1", recipient="translation:Localizer", content="done"))
        msg = await bus.receive("agent-2", timeout=5.0)
    """

    def __init__(self) -> None:
        # agent_id -> address string
        self._agents: dict[str, str] = {}
        # agent_id -> parsed AgentAddress
        self._addresses: dict[str, AgentAddress] = {}
        # agent_id -> asyncio.Queue of AgentMessage
        self._mailboxes: dict[str, asyncio.Queue[AgentMessage]] = {}
        # event_name -> list of (agent_id, handler)
        self._subscribers: dict[str, list[tuple[str, Callable]]] = defaultdict(list)

    def register_agent(self, agent_id: str, address: str) -> None:
        """
        Register an agent on the bus.

        Args:
            agent_id: Unique agent instance ID.
            address: Pipeline address (e.g. "translation:Localizer:0").
        """
        self._agents[agent_id] = address
        self._addresses[agent_id] = AgentAddress.parse(address)
        self._mailboxes[agent_id] = asyncio.Queue()
        logger.debug("Registered agent %s at address %s", agent_id, address)

    def unregister_agent(self, agent_id: str) -> None:
        """Remove an agent from the bus."""
        self._agents.pop(agent_id, None)
        self._addresses.pop(agent_id, None)
        self._mailboxes.pop(agent_id, None)
        # Remove from all subscriber lists
        for event_name in list(self._subscribers):
            self._subscribers[event_name] = [
                (aid, handler)
                for aid, handler in self._subscribers[event_name]
                if aid != agent_id
            ]

    async def send(self, message: AgentMessage) -> int:
        """
        Send a message to one or more agents.

        The recipient field can be:
        - An agent_id (direct delivery)
        - An address pattern (delivered to all matching agents)

        Args:
            message: The message to send.

        Returns:
            Number of agents the message was delivered to.
        """
        delivered = 0

        # Try direct agent_id match first
        if message.recipient in self._mailboxes:
            await self._mailboxes[message.recipient].put(message)
            return 1

        # Pattern-based routing
        for agent_id, addr in self._addresses.items():
            if addr.matches(message.recipient):
                if agent_id in self._mailboxes:
                    await self._mailboxes[agent_id].put(message)
                    delivered += 1

        if delivered == 0:
            logger.warning("No agents matched recipient '%s'", message.recipient)

        return delivered

    async def receive(
        self,
        agent_id: str,
        timeout: float = 30.0,
    ) -> Optional[AgentMessage]:
        """
        Receive the next message for an agent.

        Blocks until a message arrives or timeout is reached.

        Args:
            agent_id: The agent to receive for.
            timeout: Maximum wait time in seconds.

        Returns:
            AgentMessage if received, None on timeout.
        """
        mailbox = self._mailboxes.get(agent_id)
        if mailbox is None:
            logger.warning("Agent %s is not registered on the bus", agent_id)
            return None

        try:
            return await asyncio.wait_for(mailbox.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def peek(self, agent_id: str) -> int:
        """Check how many messages are waiting in an agent's mailbox."""
        mailbox = self._mailboxes.get(agent_id)
        return mailbox.qsize() if mailbox else 0

    async def broadcast(self, event: AgentEvent) -> None:
        """
        Broadcast an event to all subscribed agents.

        Handlers are called concurrently but errors are logged and swallowed.
        """
        subscribers = self._subscribers.get(event.event_name, [])
        if not subscribers:
            return

        tasks = []
        for agent_id, handler in subscribers:
            tasks.append(self._safe_call(handler, event, agent_id))

        if tasks:
            await asyncio.gather(*tasks)

    def subscribe(
        self,
        agent_id: str,
        event_name: str,
        handler: Callable,
    ) -> None:
        """
        Subscribe to broadcast events.

        Args:
            agent_id: The subscribing agent's ID.
            event_name: Event name to subscribe to.
            handler: Async callable(AgentEvent) -> None.
        """
        self._subscribers[event_name].append((agent_id, handler))

    def get_registered_agents(self) -> dict[str, str]:
        """Return a copy of agent_id -> address mapping."""
        return dict(self._agents)

    @staticmethod
    async def _safe_call(handler: Callable, event: AgentEvent, agent_id: str) -> None:
        """Call a handler with error suppression."""
        try:
            await handler(event)
        except Exception:
            logger.exception("Event handler failed for agent %s on event %s", agent_id, event.event_name)
