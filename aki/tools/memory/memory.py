"""
Long-term memory tools.

Human-readable .md files with YAML frontmatter stored in a configurable
directory.  The agent uses these tools to build and maintain a persistent
knowledge base across sessions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.registry import ToolRegistry


def _memory_dir() -> Path:
    """Return the resolved memory directory from settings."""
    from aki.config.settings import get_settings

    return Path(get_settings().memory.long_term_memory_dir).expanduser().resolve()


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split a markdown file into (frontmatter_dict, body_text).

    Returns an empty dict if no valid frontmatter is found.
    """
    if not text.startswith("---"):
        return {}, text

    end = text.find("---", 3)
    if end == -1:
        return {}, text

    raw_yaml = text[3:end].strip()
    body = text[end + 3:].lstrip("\n")

    try:
        meta = yaml.safe_load(raw_yaml)
    except yaml.YAMLError:
        return {}, text

    if not isinstance(meta, dict):
        return {}, text

    return meta, body


def _build_file_content(
    *,
    name: str,
    description: str,
    body: str,
    memory_type: str = "notes",
    tags: list[str] | None = None,
) -> str:
    """Construct a complete markdown file with YAML frontmatter."""
    meta: dict[str, Any] = {
        "name": name,
        "description": description,
        "type": memory_type,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if tags:
        meta["tags"] = tags

    front = yaml.dump(meta, allow_unicode=True, default_flow_style=False, sort_keys=False).strip()
    return f"---\n{front}\n---\n\n{body}\n"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@ToolRegistry.register
class MemoryListTool(BaseTool):
    """List all long-term memory entries with their names and descriptions."""

    name = "memory_list"
    description = (
        "List available long-term memory entries. "
        "Returns name, description, and last-updated timestamp for each."
    )
    parameters: list[ToolParameter] = []
    concurrency_safe = True

    async def execute(self, **kwargs: Any) -> ToolResult:
        base = _memory_dir()
        if not base.exists():
            return ToolResult.ok(data={"memories": [], "count": 0})

        entries: list[dict[str, Any]] = []
        for path in sorted(base.glob("*.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            meta, _ = _parse_frontmatter(text)
            if not meta.get("name"):
                continue
            entries.append(
                {
                    "name": meta["name"],
                    "description": meta.get("description", ""),
                    "filename": path.name,
                    "updated_at": str(meta.get("updated_at", "")),
                }
            )

        # Sort by updated_at descending (most recent first)
        entries.sort(key=lambda e: e["updated_at"], reverse=True)

        return ToolResult.ok(data={"memories": entries, "count": len(entries)})


@ToolRegistry.register
class MemoryReadTool(BaseTool):
    """Read the full content of a specific long-term memory entry."""

    name = "memory_read"
    description = (
        "Read a long-term memory entry by name. "
        "Returns the frontmatter metadata and full body content."
    )
    parameters = [
        ToolParameter(
            name="memory_name",
            type="string",
            description="Name of the memory entry to read (without .md extension)",
        ),
    ]
    concurrency_safe = True

    async def execute(self, memory_name: str, **kwargs: Any) -> ToolResult:
        base = _memory_dir()
        path = base / f"{memory_name}.md"

        if not path.resolve().is_relative_to(base.resolve()):
            return ToolResult.fail(f"Invalid memory name: {memory_name}")

        if not path.exists():
            return ToolResult.fail(f"Memory '{memory_name}' not found")

        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:
            return ToolResult.fail(f"Failed to read memory: {exc}")

        meta, body = _parse_frontmatter(text)
        return ToolResult.ok(
            data={
                "name": meta.get("name", memory_name),
                "description": meta.get("description", ""),
                "type": meta.get("type", "notes"),
                "updated_at": str(meta.get("updated_at", "")),
                "tags": meta.get("tags", []),
                "body": body,
            }
        )


@ToolRegistry.register
class MemoryWriteTool(BaseTool):
    """Create or update a long-term memory entry."""

    name = "memory_write"
    description = (
        "Create or update a long-term memory entry. "
        "The entry is stored as a .md file with YAML frontmatter. "
        "Use this to persist user preferences, personality traits, "
        "relationship goals, or any knowledge worth remembering across sessions."
    )
    parameters = [
        ToolParameter(
            name="memory_name",
            type="string",
            description="Identifier for the memory (used as filename, e.g. 'user-profile')",
        ),
        ToolParameter(
            name="description",
            type="string",
            description="One-line summary of what this memory contains (used for indexing)",
        ),
        ToolParameter(
            name="body",
            type="string",
            description="Full markdown content of the memory entry",
        ),
        ToolParameter(
            name="type",
            type="string",
            description="Category: profile, preferences, history, notes (default: notes)",
            required=False,
            default="notes",
        ),
        ToolParameter(
            name="tags",
            type="string",
            description="Comma-separated tags for categorization (optional)",
            required=False,
        ),
    ]

    async def execute(
        self,
        memory_name: str,
        description: str,
        body: str,
        type: str = "notes",
        tags: str = "",
        **kwargs: Any,
    ) -> ToolResult:
        base = _memory_dir()
        base.mkdir(parents=True, exist_ok=True)

        path = base / f"{memory_name}.md"

        if not path.resolve().is_relative_to(base.resolve()):
            return ToolResult.fail(f"Invalid memory name: {memory_name}")

        action = "updated" if path.exists() else "created"

        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None

        content = _build_file_content(
            name=memory_name,
            description=description,
            body=body,
            memory_type=type,
            tags=tag_list,
        )

        try:
            path.write_text(content, encoding="utf-8")
        except Exception as exc:
            return ToolResult.fail(f"Failed to write memory: {exc}")

        return ToolResult.ok(
            data={
                "filename": path.name,
                "action": action,
                "memory_name": memory_name,
            }
        )
