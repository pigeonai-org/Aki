"""
Personality registry — discovery, loading, and validation.

Scans aki/personality/<name>/<name>.md for personality definitions.
Each personality is a YAML-frontmatter Markdown file with optional
supplementary files (story.md, examples.md).

The base layer (base.md) is always loaded first and cannot be overridden
by individual personalities. It establishes the non-negotiable foundation:
AI self-awareness, purpose, and universal interaction principles.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Resolve the personality directory relative to this file
PERSONALITY_DIR = Path(__file__).parent

# Required frontmatter fields
_REQUIRED_FIELDS = {"name", "display_name", "description", "language", "mbti", "voice", "traits"}


@dataclass
class InteractionMode:
    """Controls how the personality approaches work and user interaction.

    These settings will feed into the future proactivity/autonomy system.
    """

    # How much initiative the agent takes (0.0 = fully reactive, 1.0 = fully proactive)
    proactivity: float = 0.7

    # When to confirm before acting
    # "always" = ask before every action
    # "destructive" = ask only before irreversible/costly actions (default)
    # "never" = just do it (for trusted automated pipelines)
    confirm: str = "destructive"

    # Communication density
    # "minimal" = terse, results-only
    # "balanced" = explain when useful, skip when obvious (default)
    # "verbose" = always explain reasoning
    detail: str = "balanced"

    # Error handling approach
    # "ask" = report error and wait for guidance
    # "retry" = try alternatives before asking (default)
    # "persist" = keep trying until exhausted
    error_strategy: str = "retry"

    # Task approach
    # "methodical" = step by step, thorough
    # "adaptive" = adjust approach based on context (default)
    # "creative" = explore unconventional solutions
    approach: str = "adaptive"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InteractionMode:
        """Create from a dict, ignoring unknown keys."""
        known = {"proactivity", "confirm", "detail", "error_strategy", "approach"}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class Personality:
    """A loaded personality definition."""

    # Required
    name: str
    display_name: str
    description: str
    language: str
    mbti: str
    voice: list[str]
    traits: list[str]

    # Interaction mode — controls work behavior and proactivity
    interaction_mode: InteractionMode = field(default_factory=InteractionMode)

    # Optional identity
    aliases: list[str] = field(default_factory=list)
    age: int | str | None = None
    gender: str | None = None
    nationality: str | None = None

    # Optional preferences
    interests: list[str] = field(default_factory=list)
    likes: list[str] = field(default_factory=list)
    dislikes: list[str] = field(default_factory=list)

    # Optional depth
    emotional_profile: dict[str, Any] = field(default_factory=dict)
    knowledge_domains: dict[str, list[str]] = field(default_factory=dict)
    boundaries: list[dict[str, str]] = field(default_factory=list)
    quirks: list[str] = field(default_factory=list)
    relationships: list[dict[str, str]] = field(default_factory=list)
    worldview: list[str] = field(default_factory=list)
    motivation: str = ""
    growth_arc: str = ""

    # Loaded content
    persona_prompt: str = ""  # Markdown body of main file
    story: str | None = None  # Content of story.md
    examples: str | None = None  # Content of examples.md

    # Filesystem
    directory: Path | None = None

    def to_system_prompt(self, persona_memory_overlay: str = "") -> str:
        """Build the full system prompt: base → interaction_mode → persona → memory overlay."""
        parts: list[str] = []

        # 1. Base layer (non-negotiable)
        base_text = _load_base()
        if base_text:
            parts.append(base_text)

        # 2. Interaction mode
        im = self.interaction_mode
        mode_desc = (
            f"[Interaction Mode: proactivity={im.proactivity}, "
            f"confirm={im.confirm}, detail={im.detail}, "
            f"error_strategy={im.error_strategy}, approach={im.approach}]"
        )
        parts.append(mode_desc)

        # 3. Core persona
        if self.persona_prompt:
            parts.append(self.persona_prompt.strip())

        # 4. Structured attributes
        if self.voice:
            parts.append(f"[Voice: {'、'.join(self.voice)}]")

        if self.traits:
            parts.append(f"[Traits: {'、'.join(self.traits)}]")

        if self.mbti:
            parts.append(f"[MBTI: {self.mbti}]")

        if self.emotional_profile:
            baseline = self.emotional_profile.get("baseline", "")
            triggers = self.emotional_profile.get("triggers", [])
            if baseline or triggers:
                lines = []
                if baseline:
                    lines.append(f"  baseline: {baseline}")
                for t in triggers:
                    lines.append(f"  - {t['topic']} → {t['reaction']}")
                parts.append("[Emotional Profile:\n" + "\n".join(lines) + "]")

        if self.boundaries:
            lines = [f"  - {b['topic']}: {b['handling']}" for b in self.boundaries]
            parts.append("[Boundaries:\n" + "\n".join(lines) + "]")

        if self.quirks:
            parts.append("[Quirks: " + "; ".join(self.quirks) + "]")

        if self.knowledge_domains:
            lines = []
            for level, domains in self.knowledge_domains.items():
                if domains:
                    lines.append(f"  {level}: {', '.join(domains)}")
            if lines:
                parts.append("[Knowledge:\n" + "\n".join(lines) + "]")

        # 5. Dynamic persona memory overlay (relationship + evolution)
        if persona_memory_overlay:
            parts.append("--- DYNAMIC PERSONALITY (from relationship history) ---")
            parts.append(persona_memory_overlay)

        return "\n\n".join(parts)

    def get_story(self) -> str | None:
        """Load story on demand if not already loaded."""
        if self.story is not None:
            return self.story
        if self.directory:
            story_path = self.directory / "story.md"
            if story_path.exists():
                self.story = story_path.read_text(encoding="utf-8")
                return self.story
        return None

    def get_examples(self) -> str | None:
        """Load examples on demand if not already loaded."""
        if self.examples is not None:
            return self.examples
        if self.directory:
            examples_path = self.directory / "examples.md"
            if examples_path.exists():
                self.examples = examples_path.read_text(encoding="utf-8")
                return self.examples
        return None


@lru_cache(maxsize=1)
def _load_base() -> str:
    """Load the base personality layer. Cached — loaded once."""
    base_path = PERSONALITY_DIR / "base.md"
    if not base_path.exists():
        logger.warning("base.md not found at %s", base_path)
        return ""
    text = base_path.read_text(encoding="utf-8")
    # Strip the markdown title line if present
    lines = text.strip().split("\n")
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    return "\n".join(lines).strip()


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Extract YAML frontmatter and body from markdown text."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("---", 3)
    if end == -1:
        return {}, text
    try:
        meta = yaml.safe_load(text[3:end].strip())
    except yaml.YAMLError:
        return {}, text
    body = text[end + 3:].strip()
    return (meta if isinstance(meta, dict) else {}), body


def load_personality(name: str, base_dir: Path | None = None) -> Personality | None:
    """Load a personality by name from its directory."""
    base = base_dir or PERSONALITY_DIR
    persona_dir = base / name

    if not persona_dir.is_dir():
        logger.warning("Personality directory not found: %s", persona_dir)
        return None

    main_file = persona_dir / f"{name}.md"
    if not main_file.exists():
        logger.warning("Personality file not found: %s", main_file)
        return None

    text = main_file.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)

    # Validate required fields
    missing = _REQUIRED_FIELDS - set(meta.keys())
    if missing:
        logger.warning("Personality '%s' missing required fields: %s", name, missing)
        return None

    # Parse interaction_mode
    im_data = meta.get("interaction_mode", {})
    interaction_mode = InteractionMode.from_dict(im_data) if im_data else InteractionMode()

    # Build Personality object
    personality = Personality(
        name=meta["name"],
        display_name=meta["display_name"],
        description=meta["description"],
        language=meta["language"],
        mbti=meta["mbti"],
        voice=meta.get("voice", []),
        traits=meta.get("traits", []),
        interaction_mode=interaction_mode,
        aliases=meta.get("aliases", []),
        age=meta.get("age"),
        gender=meta.get("gender"),
        nationality=meta.get("nationality"),
        interests=meta.get("interests", []),
        likes=meta.get("likes", []),
        dislikes=meta.get("dislikes", []),
        emotional_profile=meta.get("emotional_profile", {}),
        knowledge_domains=meta.get("knowledge_domains", {}),
        boundaries=meta.get("boundaries", []),
        quirks=meta.get("quirks", []),
        relationships=meta.get("relationships", []),
        worldview=meta.get("worldview", []),
        motivation=meta.get("motivation", ""),
        growth_arc=meta.get("growth_arc", ""),
        persona_prompt=body,
        directory=persona_dir,
    )

    return personality


def discover_personalities(base_dir: Path | None = None) -> list[Personality]:
    """Discover all valid personalities in the personality directory."""
    base = base_dir or PERSONALITY_DIR
    personalities: list[Personality] = []

    if not base.exists():
        return personalities

    for entry in sorted(base.iterdir()):
        if not entry.is_dir() or entry.name.startswith("_"):
            continue
        personality = load_personality(entry.name, base_dir=base)
        if personality:
            personalities.append(personality)

    return personalities


def get_personality(name: str, base_dir: Path | None = None) -> Personality:
    """Load a personality by name. Raises ValueError if not found."""
    personality = load_personality(name, base_dir=base_dir)
    if personality is None:
        available = [p.name for p in discover_personalities(base_dir=base_dir)]
        raise ValueError(
            f"Personality '{name}' not found. Available: {available}"
        )
    return personality
