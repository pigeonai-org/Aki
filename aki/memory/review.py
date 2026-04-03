"""
Memory review pass — post-session analysis and promotion to long-term memory.

After a session ends, the review pass:
    1. Analyzes the conversation for significant information
    2. Updates User Memory with new personal facts
    3. Creates an Episodic Memory entry (session summary)
    4. Updates Persona Memory (bond changes, events, trait modifiers)
    5. Extracts Procedural Memory rules (work preferences)
    6. Semantic memory is handled separately (auto-captured during session)

The review uses an LLM for analysis, making it a lightweight but intelligent process.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ReviewResult:
    """What the review pass decided to do."""
    user_facts_added: list[str] = field(default_factory=list)
    episodic_summary: str = ""
    episodic_key_decisions: list[str] = field(default_factory=list)
    episodic_topics: list[str] = field(default_factory=list)
    episodic_emotional_tone: str = ""
    bond_updates: dict[str, Any] = field(default_factory=dict)
    new_events: list[dict[str, Any]] = field(default_factory=list)
    trait_modifiers: list[dict[str, Any]] = field(default_factory=list)
    procedural_rules: list[dict[str, Any]] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""


REVIEW_PROMPT = """You are a memory analyst. Analyze the following conversation and extract information for long-term storage.

Conversation:
{conversation}

Current user profile:
{user_profile}

Current relationship state:
{relationship_state}

Analyze this conversation and return a JSON object with these fields:

{{
    "user_facts": ["list of NEW facts about the user (skip if already known)"],
    "session_summary": "1-2 sentence summary of what happened",
    "key_decisions": ["important decisions made"],
    "topics": ["topic keywords"],
    "emotional_tone": "overall emotional tone of the conversation",
    "bond_change": {{
        "closeness_delta": 0.0,
        "new_sentiment": "",
        "new_descriptors": [],
        "new_trust_areas": [],
        "stage_advance": false
    }},
    "personality_events": [
        {{
            "summary": "what happened",
            "emotional_impact": "how it affected the persona",
            "category": "milestone|conflict|revelation|shared_experience|turning_point",
            "personality_effect": "optional: how this changes the persona"
        }}
    ],
    "trait_changes": [
        {{
            "trait": "trait name",
            "direction": "amplify|soften|new|suppress",
            "degree": 0.0,
            "reason": "why this shift"
        }}
    ],
    "procedural_rules": [
        {{
            "rule": "preference description",
            "confidence": 0.0,
            "source": "how you inferred this"
        }}
    ]
}}

Only include fields where you found meaningful information. Return empty lists/objects for dimensions with no updates. Be conservative — only record things that are clearly significant, not trivial small talk."""


class MemoryReviewer:
    """Runs the post-session review pass."""

    def __init__(
        self,
        user_store: Any = None,
        episodic_store: Any = None,
        procedural_store: Any = None,
        persona_bridge: Any = None,
    ):
        self.user_store = user_store
        self.episodic_store = episodic_store
        self.procedural_store = procedural_store
        self.persona_bridge = persona_bridge

    async def review(
        self,
        session_id: str,
        user_id: str,
        messages: list[dict[str, Any]],
        personality_name: str = "aki",
        llm: Any = None,
    ) -> ReviewResult:
        """Analyze a completed session and promote to long-term memory.

        Args:
            session_id: The session being reviewed.
            user_id: The user who participated.
            messages: The full conversation history.
            personality_name: Active personality during the session.
            llm: LLM instance for analysis. If None, skip LLM analysis.

        Returns:
            ReviewResult describing all changes made.
        """
        result = ReviewResult()

        # Skip trivial conversations
        user_messages = [m for m in messages if m.get("role") == "user"]
        if len(user_messages) < 2:
            result.skipped = True
            result.skip_reason = "Too few user messages to review"
            return result

        # Build conversation text for analysis
        conversation_text = self._format_conversation(messages, max_messages=50)

        # Get current state for context
        user_profile = ""
        if self.user_store:
            try:
                user_profile = self.user_store.to_context(user_id)
            except Exception:
                pass

        relationship_state = ""
        if self.persona_bridge:
            try:
                relationship_state = self.persona_bridge.to_context(user_id)
            except Exception:
                pass

        # Run LLM analysis
        if llm is None:
            # Without LLM, do basic extraction only
            result = self._basic_review(messages, session_id)
        else:
            result = await self._llm_review(
                llm, conversation_text, user_profile, relationship_state, session_id
            )

        # Apply results to stores
        self._apply_results(result, user_id, session_id, personality_name)

        return result

    def _format_conversation(self, messages: list[dict[str, Any]], max_messages: int = 50) -> str:
        """Format conversation for LLM analysis."""
        recent = messages[-max_messages:]
        lines = []
        for msg in recent:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            # Truncate very long messages
            if len(content) > 500:
                content = content[:500] + "..."
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def _basic_review(self, messages: list[dict[str, Any]], session_id: str) -> ReviewResult:
        """Basic review without LLM — just create an episodic entry."""
        result = ReviewResult()

        user_msgs = [m.get("content", "") for m in messages if m.get("role") == "user"]
        if user_msgs:
            # Simple summary: first and last user messages
            first = user_msgs[0][:100]
            result.episodic_summary = f"Conversation starting with: {first}"

        return result

    async def _llm_review(
        self,
        llm: Any,
        conversation: str,
        user_profile: str,
        relationship_state: str,
        session_id: str,
    ) -> ReviewResult:
        """Full LLM-powered review."""
        import json

        result = ReviewResult()

        prompt = REVIEW_PROMPT.format(
            conversation=conversation,
            user_profile=user_profile or "(no existing profile)",
            relationship_state=relationship_state or "(new relationship)",
        )

        try:
            response = await llm.chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
            )

            # Parse JSON from response
            content = response.content if hasattr(response, "content") else str(response)

            # Extract JSON from response (might be wrapped in ```json blocks)
            json_str = content
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0]
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0]

            data = json.loads(json_str.strip())

            result.user_facts_added = data.get("user_facts", [])
            result.episodic_summary = data.get("session_summary", "")
            result.episodic_key_decisions = data.get("key_decisions", [])
            result.episodic_topics = data.get("topics", [])
            result.episodic_emotional_tone = data.get("emotional_tone", "")
            result.bond_updates = data.get("bond_change", {})
            result.new_events = data.get("personality_events", [])
            result.trait_modifiers = data.get("trait_changes", [])
            result.procedural_rules = data.get("procedural_rules", [])

        except Exception as e:
            logger.warning("LLM review failed, falling back to basic: %s", e)
            # Don't lose the session — at least create a basic episodic entry
            result.episodic_summary = f"Session {session_id} (LLM review failed)"

        return result

    def _apply_results(
        self,
        result: ReviewResult,
        user_id: str,
        session_id: str,
        personality_name: str,
    ) -> None:
        """Apply review results to the appropriate memory stores."""
        now = datetime.now(timezone.utc).isoformat()

        # 1. User Memory — add new facts
        if self.user_store and result.user_facts_added:
            try:
                for fact in result.user_facts_added:
                    self.user_store.add_fact(user_id, fact)
                logger.info("Added %d user facts", len(result.user_facts_added))
            except Exception as e:
                logger.warning("Failed to update user memory: %s", e)

        # 2. Episodic Memory — add session summary
        if self.episodic_store and result.episodic_summary:
            try:
                self.episodic_store.add_episode(
                    user_id=user_id,
                    session_id=session_id,
                    summary=result.episodic_summary,
                    key_decisions=result.episodic_key_decisions,
                    outcome="",
                    topics=result.episodic_topics,
                    emotional_tone=result.episodic_emotional_tone,
                )
                logger.info("Added episodic entry for session %s", session_id)
            except Exception as e:
                logger.warning("Failed to update episodic memory: %s", e)

        # 3. Persona Memory — update bond and events
        if self.persona_bridge:
            try:
                if result.bond_updates:
                    self.persona_bridge.update(user_id, bond=result.bond_updates)
                # Events and trait modifiers need the full manager
                if result.new_events or result.trait_modifiers:
                    from aki.personality.persona_memory.manager import (
                        PersonaMemoryManager, KeyEvent, TraitModifier,
                    )
                    mgr = PersonaMemoryManager(personality_name, user_id)
                    memory = mgr.load()

                    for event_data in result.new_events:
                        event = KeyEvent(
                            timestamp=now,
                            summary=event_data.get("summary", ""),
                            emotional_impact=event_data.get("emotional_impact", ""),
                            category=event_data.get("category", "shared_experience"),
                            personality_effect=event_data.get("personality_effect", ""),
                        )
                        mgr.add_event(memory, event)

                    for mod_data in result.trait_modifiers:
                        modifier = TraitModifier(
                            trait=mod_data.get("trait", ""),
                            direction=mod_data.get("direction", "amplify"),
                            degree=mod_data.get("degree", 0.5),
                            reason=mod_data.get("reason", ""),
                            since=now[:10],
                        )
                        mgr.add_trait_modifier(memory, modifier)

            except Exception as e:
                logger.warning("Failed to update persona memory: %s", e)

        # 4. Procedural Memory — add rules
        if self.procedural_store and result.procedural_rules:
            try:
                for rule_data in result.procedural_rules:
                    self.procedural_store.add_rule(
                        user_id=user_id,
                        rule=rule_data.get("rule", ""),
                        confidence=rule_data.get("confidence", 0.7),
                        source=rule_data.get("source", "inferred from conversation"),
                    )
                logger.info("Added %d procedural rules", len(result.procedural_rules))
            except Exception as e:
                logger.warning("Failed to update procedural memory: %s", e)
