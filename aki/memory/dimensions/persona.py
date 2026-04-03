"""Bridge to the persona memory system in aki.personality.persona_memory."""
from __future__ import annotations

import logging
from typing import Any

from aki.memory.dimensions.base import DimensionStore

logger = logging.getLogger(__name__)


class PersonaDimensionBridge(DimensionStore):
    """Wraps PersonaMemoryManager as a memory dimension."""

    dimension = "persona"

    def __init__(self, personality_name: str = "aki"):
        self.personality_name = personality_name

    def load(self, user_id: str) -> dict[str, Any]:
        from aki.personality.persona_memory.manager import PersonaMemoryManager

        mgr = PersonaMemoryManager(self.personality_name, user_id)
        memory = mgr.load()
        return {
            "bond": {
                "stage": memory.bond.stage,
                "closeness": memory.bond.closeness,
                "sentiment": memory.bond.current_sentiment,
            },
            "events_count": len(memory.events),
            "trait_modifiers": [
                {"trait": m.trait, "direction": m.direction, "degree": m.degree}
                for m in memory.trait_modifiers
            ],
        }

    def save(self, user_id: str, data: dict[str, Any]) -> None:
        # Persona memory has its own save mechanism via PersonaMemoryManager
        pass

    def to_context(self, user_id: str) -> str:
        from aki.personality.persona_memory.manager import PersonaMemoryManager

        mgr = PersonaMemoryManager(self.personality_name, user_id)
        memory = mgr.load()
        return memory.to_system_prompt_overlay()

    def update(self, user_id: str, **kwargs: Any) -> None:
        from aki.personality.persona_memory.manager import PersonaMemoryManager

        mgr = PersonaMemoryManager(self.personality_name, user_id)
        memory = mgr.load()
        if "bond" in kwargs:
            mgr.update_bond(memory, **kwargs["bond"])
