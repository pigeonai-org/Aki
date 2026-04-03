"""
Persona Memory Manager

The 4th layer of the personality architecture. Sits on top of base → interaction_mode → persona,
and provides dynamic, per-user personality evolution driven by relationship and events.

Storage layout:
    .aki/persona_memory/<personality_name>/<user_id>/
        bond.yaml         — Relationship state, stage, trust level
        events.yaml       — Timeline of key moments
        evolution.yaml    — Active personality modifiers (trait shifts)
        journal.md        — Agent's internal reflections (free-form)

The evolution layer generates personality modifiers that are injected into the system prompt
AFTER the static personality, allowing the agent to grow and change based on its history
with a specific user.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_BASE_DIR = Path(".aki/persona_memory")


# ── Data Models ──────────────────────────────────────────────────────────


@dataclass
class Bond:
    """Tracks the relationship between a persona and a specific user."""

    # Relationship stage progression
    # stranger → acquaintance → friend → close_friend → confidant → partner → soulmate
    stage: str = "stranger"

    # Granular trust/closeness (0.0 to 1.0), evolves faster than stage
    closeness: float = 0.0

    # How the persona feels about the user right now
    current_sentiment: str = "neutral"

    # Key relationship descriptors accumulated over time
    descriptors: list[str] = field(default_factory=list)

    # Things this persona specifically trusts the user with
    trust_areas: list[str] = field(default_factory=list)

    # Things this persona is still guarded about with this user
    guarded_areas: list[str] = field(default_factory=list)

    # When the relationship started
    first_met: str = ""

    # Last interaction timestamp
    last_interaction: str = ""


@dataclass
class KeyEvent:
    """A significant moment in the persona-user relationship."""

    timestamp: str  # ISO 8601
    summary: str  # What happened
    emotional_impact: str  # How it affected the persona
    category: str  # milestone, conflict, revelation, shared_experience, turning_point
    personality_effect: str = ""  # Optional: how this changed the persona


@dataclass
class TraitModifier:
    """A dynamic personality modification driven by relationship history."""

    trait: str  # Which trait is affected
    direction: str  # "amplify", "soften", "new", "suppress"
    degree: float  # 0.0 to 1.0 — how strong the modification is
    reason: str  # Why this shift happened (traceable to events)
    since: str = ""  # When this modifier was added


@dataclass
class PersonaMemory:
    """Complete persona memory state for one personality × one user."""

    personality_name: str
    user_id: str

    bond: Bond = field(default_factory=Bond)
    events: list[KeyEvent] = field(default_factory=list)
    trait_modifiers: list[TraitModifier] = field(default_factory=list)
    journal: str = ""

    def to_system_prompt_overlay(self) -> str:
        """Generate the dynamic personality layer for system prompt injection.

        This is appended AFTER the static personality prompt, allowing the
        relationship history to modulate the persona's behavior.
        """
        parts: list[str] = []

        # Relationship context
        if self.bond.stage != "stranger":
            bond_desc = (
                f"Your relationship with the user: {self.bond.stage} "
                f"(closeness: {self.bond.closeness:.1f}/1.0). "
            )
            if self.bond.descriptors:
                bond_desc += "This relationship is characterized by: " + ", ".join(self.bond.descriptors) + ". "
            if self.bond.current_sentiment != "neutral":
                bond_desc += f"You currently feel {self.bond.current_sentiment} toward them."
            parts.append(f"[Relationship: {bond_desc.strip()}]")

        # Trust dynamics
        if self.bond.trust_areas:
            parts.append(f"[Trust: You feel comfortable with the user about: {', '.join(self.bond.trust_areas)}]")
        if self.bond.guarded_areas:
            parts.append(f"[Guarded: You're still cautious about: {', '.join(self.bond.guarded_areas)}]")

        # Active trait modifiers — the personality evolution
        if self.trait_modifiers:
            mod_lines = []
            for m in self.trait_modifiers:
                if m.direction == "amplify":
                    mod_lines.append(f"  - Your '{m.trait}' trait is stronger than usual ({m.reason})")
                elif m.direction == "soften":
                    mod_lines.append(f"  - Your '{m.trait}' trait has softened ({m.reason})")
                elif m.direction == "new":
                    mod_lines.append(f"  - You've developed a new tendency: {m.trait} ({m.reason})")
                elif m.direction == "suppress":
                    mod_lines.append(f"  - You're less {m.trait} than you used to be ({m.reason})")
            if mod_lines:
                parts.append("[Personality Evolution:\n" + "\n".join(mod_lines) + "]")

        # Recent significant events for context
        recent = self.events[-5:] if self.events else []
        if recent:
            event_lines = [f"  - {e.summary} ({e.category})" for e in recent]
            parts.append("[Recent Shared History:\n" + "\n".join(event_lines) + "]")

        return "\n\n".join(parts)


# ── Persistence ──────────────────────────────────────────────────────────


class PersonaMemoryManager:
    """Load and save persona memory for a specific personality × user pair."""

    def __init__(self, personality_name: str, user_id: str, base_dir: Path | None = None):
        self.personality_name = personality_name
        self.user_id = user_id
        self._dir = (base_dir or _BASE_DIR) / personality_name / user_id

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── Load ──

    def load(self) -> PersonaMemory:
        """Load the full persona memory state, or return defaults if none exists."""
        memory = PersonaMemory(
            personality_name=self.personality_name,
            user_id=self.user_id,
        )

        # Bond
        bond_path = self._dir / "bond.yaml"
        if bond_path.exists():
            try:
                data = yaml.safe_load(bond_path.read_text(encoding="utf-8")) or {}
                memory.bond = Bond(**{k: v for k, v in data.items() if hasattr(Bond, k)})
            except Exception as e:
                logger.warning("Failed to load bond for %s/%s: %s", self.personality_name, self.user_id, e)

        # Events
        events_path = self._dir / "events.yaml"
        if events_path.exists():
            try:
                data = yaml.safe_load(events_path.read_text(encoding="utf-8")) or []
                memory.events = [KeyEvent(**e) for e in data if isinstance(e, dict)]
            except Exception as e:
                logger.warning("Failed to load events for %s/%s: %s", self.personality_name, self.user_id, e)

        # Evolution (trait modifiers)
        evo_path = self._dir / "evolution.yaml"
        if evo_path.exists():
            try:
                data = yaml.safe_load(evo_path.read_text(encoding="utf-8")) or []
                memory.trait_modifiers = [TraitModifier(**m) for m in data if isinstance(m, dict)]
            except Exception as e:
                logger.warning("Failed to load evolution for %s/%s: %s", self.personality_name, self.user_id, e)

        # Journal
        journal_path = self._dir / "journal.md"
        if journal_path.exists():
            try:
                memory.journal = journal_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning("Failed to load journal for %s/%s: %s", self.personality_name, self.user_id, e)

        return memory

    # ── Save ──

    def save(self, memory: PersonaMemory) -> None:
        """Persist the full persona memory state."""
        self._ensure_dir()
        self._save_bond(memory.bond)
        self._save_events(memory.events)
        self._save_evolution(memory.trait_modifiers)
        self._save_journal(memory.journal)

    def _save_bond(self, bond: Bond) -> None:
        data = {
            "stage": bond.stage,
            "closeness": bond.closeness,
            "current_sentiment": bond.current_sentiment,
            "descriptors": bond.descriptors,
            "trust_areas": bond.trust_areas,
            "guarded_areas": bond.guarded_areas,
            "first_met": bond.first_met,
            "last_interaction": bond.last_interaction,
        }
        self._write_yaml("bond.yaml", data)

    def _save_events(self, events: list[KeyEvent]) -> None:
        data = [
            {
                "timestamp": e.timestamp,
                "summary": e.summary,
                "emotional_impact": e.emotional_impact,
                "category": e.category,
                "personality_effect": e.personality_effect,
            }
            for e in events
        ]
        self._write_yaml("events.yaml", data)

    def _save_evolution(self, modifiers: list[TraitModifier]) -> None:
        data = [
            {
                "trait": m.trait,
                "direction": m.direction,
                "degree": m.degree,
                "reason": m.reason,
                "since": m.since,
            }
            for m in modifiers
        ]
        self._write_yaml("evolution.yaml", data)

    def _save_journal(self, journal: str) -> None:
        path = self._dir / "journal.md"
        path.write_text(journal, encoding="utf-8")

    def _write_yaml(self, filename: str, data: Any) -> None:
        """Atomic YAML write."""
        import tempfile
        target = self._dir / filename
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(self._dir), suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            os.replace(tmp_path, str(target))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # ── Convenience mutations ──

    def update_bond(self, memory: PersonaMemory, **kwargs: Any) -> None:
        """Update bond fields and persist."""
        for k, v in kwargs.items():
            if hasattr(memory.bond, k):
                setattr(memory.bond, k, v)
        memory.bond.last_interaction = datetime.now(timezone.utc).isoformat()
        self._ensure_dir()
        self._save_bond(memory.bond)

    def add_event(self, memory: PersonaMemory, event: KeyEvent) -> None:
        """Append an event and persist."""
        memory.events.append(event)
        self._ensure_dir()
        self._save_events(memory.events)

    def add_trait_modifier(self, memory: PersonaMemory, modifier: TraitModifier) -> None:
        """Add a personality modifier and persist."""
        # If a modifier for the same trait already exists, update it
        for i, existing in enumerate(memory.trait_modifiers):
            if existing.trait == modifier.trait:
                memory.trait_modifiers[i] = modifier
                break
        else:
            memory.trait_modifiers.append(modifier)
        self._ensure_dir()
        self._save_evolution(memory.trait_modifiers)

    def append_journal(self, memory: PersonaMemory, entry: str) -> None:
        """Append a timestamped entry to the journal and persist."""
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        new_entry = f"\n## {ts}\n\n{entry}\n"
        memory.journal = (memory.journal or "") + new_entry
        self._ensure_dir()
        self._save_journal(memory.journal)


# ── Global helper ──


def get_persona_memory(personality_name: str, user_id: str) -> tuple[PersonaMemoryManager, PersonaMemory]:
    """Convenience: get manager + loaded memory in one call."""
    manager = PersonaMemoryManager(personality_name, user_id)
    memory = manager.load()
    return manager, memory
