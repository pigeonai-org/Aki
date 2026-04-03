"""Helper for injecting the memory index into the agent system prompt.

This module is NOT a tool — it provides a synchronous function that scans the
memory directory and returns a lightweight index (name + description) suitable
for embedding in the system prompt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def _parse_frontmatter_quick(text: str) -> dict[str, Any]:
    """Extract YAML frontmatter from a markdown string (fast path)."""
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end == -1:
        return {}
    try:
        meta = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return {}
    return meta if isinstance(meta, dict) else {}


def get_memory_index(limit: int = 20) -> list[dict[str, str]]:
    """Return a compact index of all memory entries.

    Each entry contains ``name``, ``description``, and ``updated_at``.
    Results are sorted by ``updated_at`` descending and capped at *limit*.
    """
    from aki.config.settings import get_settings

    base = Path(get_settings().memory.long_term_memory_dir).expanduser().resolve()
    if not base.exists():
        return []

    entries: list[dict[str, str]] = []
    for path in base.glob("*.md"):
        try:
            # Read only the first 2 KB — frontmatter should be well within that
            raw = path.read_text(encoding="utf-8")[:2048]
        except Exception:
            continue
        meta = _parse_frontmatter_quick(raw)
        name = meta.get("name")
        if not name:
            continue
        entries.append(
            {
                "name": name,
                "description": meta.get("description", ""),
                "updated_at": str(meta.get("updated_at", "")),
            }
        )

    entries.sort(key=lambda e: e["updated_at"], reverse=True)
    return entries[:limit]
