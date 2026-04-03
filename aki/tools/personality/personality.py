"""
Personality tools.

Manage agent personality via the ``aki/personality/`` package.
Personalities are directory-based: each personality is a folder containing
a main definition file (<name>.md) plus optional story.md and examples.md.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aki.personality.registry import (
    PERSONALITY_DIR,
    discover_personalities,
    load_personality,
)
from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.registry import ToolRegistry

# Track active personality name in a simple state file
_STATE_DIR = Path(".aki/personality")
_ACTIVE_FILE = _STATE_DIR / "active.json"


def _get_active_name() -> str | None:
    """Read the currently active personality name."""
    if _ACTIVE_FILE.exists():
        try:
            data = json.loads(_ACTIVE_FILE.read_text(encoding="utf-8"))
            return data.get("active")
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _set_active_name(name: str) -> None:
    """Write the currently active personality name."""
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    _ACTIVE_FILE.write_text(
        json.dumps({"active": name}, ensure_ascii=False), encoding="utf-8"
    )


@ToolRegistry.register
class PersonalityListTool(BaseTool):
    """List all available personalities and the currently active one."""

    name = "personality_list"
    description = (
        "List available personalities. "
        "Returns name, display_name, description, mbti, and traits for each, "
        "plus which one is currently active."
    )
    parameters: list[ToolParameter] = []

    async def execute(self, **kwargs: Any) -> ToolResult:
        personalities = discover_personalities()
        active = _get_active_name()

        entries = []
        for p in personalities:
            entries.append({
                "name": p.name,
                "display_name": p.display_name,
                "description": p.description,
                "mbti": p.mbti,
                "traits": p.traits,
                "has_story": (p.directory / "story.md").exists() if p.directory else False,
                "has_examples": (p.directory / "examples.md").exists() if p.directory else False,
            })

        return ToolResult.ok(
            data={
                "personalities": entries,
                "active": active,
                "count": len(entries),
            }
        )


@ToolRegistry.register
class PersonalitySelectTool(BaseTool):
    """Activate a personality by name."""

    name = "personality_select"
    description = (
        "Select and activate a personality. "
        "Pass the name of the personality directory. "
        "It will be loaded into the system prompt on the next turn."
    )
    parameters: list[ToolParameter] = [
        ToolParameter(
            name="name",
            type="string",
            description="The personality name (directory name). Use personality_list to see options.",
            required=True,
        ),
    ]

    async def execute(self, **kwargs: Any) -> ToolResult:
        name = kwargs.get("name", "")
        if not name:
            return ToolResult.fail("name parameter is required")

        personality = load_personality(name)
        if personality is None:
            available = [p.name for p in discover_personalities()]
            return ToolResult.fail(
                f"Personality '{name}' not found. Available: {available}"
            )

        _set_active_name(name)

        return ToolResult.ok(
            data={
                "activated": personality.display_name,
                "name": personality.name,
                "mbti": personality.mbti,
                "message": (
                    f"Personality '{personality.display_name}' is now active. "
                    "It will be loaded into the system prompt on the next turn."
                ),
            }
        )


@ToolRegistry.register
class PersonalityInfoTool(BaseTool):
    """Get detailed information about a specific personality."""

    name = "personality_info"
    description = (
        "Get full details of a personality including traits, voice, "
        "emotional profile, and optionally its story and speech examples."
    )
    parameters: list[ToolParameter] = [
        ToolParameter(
            name="name",
            type="string",
            description="The personality name.",
            required=True,
        ),
        ToolParameter(
            name="include_story",
            type="boolean",
            description="Whether to include the full backstory.",
            required=False,
            default=False,
        ),
        ToolParameter(
            name="include_examples",
            type="boolean",
            description="Whether to include speech examples.",
            required=False,
            default=False,
        ),
    ]

    async def execute(self, **kwargs: Any) -> ToolResult:
        name = kwargs.get("name", "")
        if not name:
            return ToolResult.fail("name parameter is required")

        personality = load_personality(name)
        if personality is None:
            return ToolResult.fail(f"Personality '{name}' not found.")

        im = personality.interaction_mode
        data: dict[str, Any] = {
            "name": personality.name,
            "display_name": personality.display_name,
            "description": personality.description,
            "language": personality.language,
            "mbti": personality.mbti,
            "voice": personality.voice,
            "traits": personality.traits,
            "interaction_mode": {
                "proactivity": im.proactivity,
                "confirm": im.confirm,
                "detail": im.detail,
                "error_strategy": im.error_strategy,
                "approach": im.approach,
            },
            "aliases": personality.aliases,
            "interests": personality.interests,
            "likes": personality.likes,
            "dislikes": personality.dislikes,
            "emotional_profile": personality.emotional_profile,
            "knowledge_domains": personality.knowledge_domains,
            "boundaries": personality.boundaries,
            "quirks": personality.quirks,
            "relationships": personality.relationships,
            "worldview": personality.worldview,
            "motivation": personality.motivation,
            "growth_arc": personality.growth_arc,
        }

        if kwargs.get("include_story"):
            data["story"] = personality.get_story()

        if kwargs.get("include_examples"):
            data["examples"] = personality.get_examples()

        return ToolResult.ok(data=data)
