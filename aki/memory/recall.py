"""
Recall pipeline — loads relevant long-term memories at session start.

Injection strategy:
    1. User Memory     → always inject (who the user is)
    2. Persona Memory   → always inject (relationship state + trait modifiers)
    3. Procedural Memory → always inject (work preferences, usually short)
    4. Episodic Memory   → inject recent N + query-relevant
    5. Semantic Memory   → inject top-K by relevance to initial context
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RecallResult:
    """Result of a recall pass — structured context ready for injection."""
    user_context: str = ""
    persona_context: str = ""
    procedural_context: str = ""
    episodic_context: str = ""
    semantic_context: str = ""

    def to_system_prompt_block(self) -> str:
        """Combine all dimensions into a single system prompt block."""
        parts: list[str] = []

        if self.user_context:
            parts.append(f"[USER PROFILE]\n{self.user_context}")

        if self.persona_context:
            parts.append(f"[RELATIONSHIP]\n{self.persona_context}")

        if self.procedural_context:
            parts.append(f"[WORK PREFERENCES]\n{self.procedural_context}")

        if self.episodic_context:
            parts.append(f"[RECENT HISTORY]\n{self.episodic_context}")

        if self.semantic_context:
            parts.append(f"[KNOWLEDGE]\n{self.semantic_context}")

        if not parts:
            return ""

        return "--- LONG-TERM MEMORY ---\n\n" + "\n\n".join(parts)

    @property
    def is_empty(self) -> bool:
        return not any([
            self.user_context,
            self.persona_context,
            self.procedural_context,
            self.episodic_context,
            self.semantic_context,
        ])


class RecallPipeline:
    """Orchestrates memory recall across all dimensions."""

    def __init__(
        self,
        user_store: Any = None,       # UserMemoryStore
        episodic_store: Any = None,    # EpisodicMemoryStore
        semantic_store: Any = None,    # SemanticMemoryStore
        procedural_store: Any = None,  # ProceduralMemoryStore
        persona_bridge: Any = None,    # PersonaDimensionBridge
    ):
        self.user_store = user_store
        self.episodic_store = episodic_store
        self.semantic_store = semantic_store
        self.procedural_store = procedural_store
        self.persona_bridge = persona_bridge

    def recall(
        self,
        user_id: str,
        query: str = "",
        episodic_limit: int = 5,
        semantic_limit: int = 10,
    ) -> RecallResult:
        """Run the full recall pipeline for a user.

        Args:
            user_id: The user identifier.
            query: Optional query for semantic search (e.g., user's first message).
            episodic_limit: Max recent episodes to include.
            semantic_limit: Max semantic entries to include.

        Returns:
            RecallResult with context strings ready for prompt injection.
        """
        result = RecallResult()

        # 1. User Memory (always)
        if self.user_store:
            try:
                result.user_context = self.user_store.to_context(user_id)
            except Exception as e:
                logger.warning("Failed to recall user memory: %s", e)

        # 2. Persona Memory (always)
        if self.persona_bridge:
            try:
                result.persona_context = self.persona_bridge.to_context(user_id)
            except Exception as e:
                logger.warning("Failed to recall persona memory: %s", e)

        # 3. Procedural Memory (always)
        if self.procedural_store:
            try:
                result.procedural_context = self.procedural_store.to_context(user_id)
            except Exception as e:
                logger.warning("Failed to recall procedural memory: %s", e)

        # 4. Episodic Memory (recent + relevant)
        if self.episodic_store:
            try:
                recent = self.episodic_store.get_recent(user_id, limit=episodic_limit)
                if recent:
                    lines = []
                    for ep in recent:
                        summary = ep.get("summary", "")
                        ts = ep.get("timestamp", "")[:10]  # date only
                        lines.append(f"  [{ts}] {summary}")
                    result.episodic_context = "\n".join(lines)
            except Exception as e:
                logger.warning("Failed to recall episodic memory: %s", e)

        # 5. Semantic Memory (by relevance)
        if self.semantic_store:
            try:
                # Use user_id as namespace for semantic search
                result.semantic_context = self.semantic_store.to_context(user_id)
            except Exception as e:
                logger.warning("Failed to recall semantic memory: %s", e)

        return result
