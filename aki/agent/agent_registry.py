"""
Agent Registry

Discovers and manages persistent agent definitions from disk and programmatic registration.
Falls back to skill-based Role definitions for backward compatibility.
"""

import logging
import os
from typing import Optional
from uuid import uuid4

from aki.agent.identity import (
    AgentDefinition,
    AgentIdentity,
)

logger = logging.getLogger(__name__)


class AgentRegistry:
    """
    Discovers and manages agent definitions.

    Sources (in priority order):
    1. Programmatically registered definitions (via register())
    2. Discovered from .aki/agents/<name>/agent.md files
    3. Fallback to existing Role system (via get_role() bridge)

    Usage::

        registry = AgentRegistry(agents_dir=".aki/agents")
        registry.register(defn)

        defn = registry.get_definition("MediaExtractor")
        identity = registry.get_or_create_identity("MediaExtractor")
    """

    def __init__(self, agents_dir: str = ".aki/agents") -> None:
        self.agents_dir = agents_dir
        self._definitions: dict[str, AgentDefinition] = {}
        self._identities: dict[str, AgentIdentity] = {}

    def register(self, definition: AgentDefinition) -> None:
        """
        Programmatically register an agent definition.

        Takes priority over disk-discovered definitions with the same name.
        """
        self._definitions[definition.name] = definition

    def get_definition(self, name: str) -> Optional[AgentDefinition]:
        """
        Get an agent definition by name.

        Args:
            name: The agent name.

        Returns:
            AgentDefinition if found, None otherwise.
        """
        return self._definitions.get(name)

    def get_or_create_identity(self, name: str) -> Optional[AgentIdentity]:
        """
        Get or create a persistent identity for an agent.

        If the agent has been seen before, returns the existing identity
        (with incremented session count). Otherwise creates a new one.

        Args:
            name: The agent name.

        Returns:
            AgentIdentity if definition exists, None otherwise.
        """
        defn = self.get_definition(name)
        if defn is None:
            return None

        if name in self._identities:
            identity = self._identities[name]
            identity.increment_session()
            return identity

        # Validate agent name to prevent path traversal
        if os.sep in name or '/' in name or '..' in name:
            raise ValueError(f"Invalid agent name: {name}")

        # Create new identity
        state_dir = os.path.join(self.agents_dir, name, "state")
        os.makedirs(state_dir, exist_ok=True)

        identity = AgentIdentity(
            agent_id=str(uuid4()),
            definition=defn,
            state_dir=state_dir,
        )
        self._identities[name] = identity
        return identity

    def list_agents(self) -> list[str]:
        """List all registered agent names."""
        return list(self._definitions.keys())

    def has_agent(self, name: str) -> bool:
        """Check if an agent definition exists."""
        return name in self._definitions

    def remove(self, name: str) -> None:
        """Remove an agent definition and its identity."""
        self._definitions.pop(name, None)
        self._identities.pop(name, None)
