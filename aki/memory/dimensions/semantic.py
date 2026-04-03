"""Semantic memory dimension — learned knowledge, facts, notes.

Bridges the existing markdown-based memory system. Each entry is a .md file
with YAML frontmatter (name, description, type, tags, updated_at) and a
markdown body.

Storage: .aki/memory/semantic/<namespace>/*.md
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from aki.memory.dimensions.base import DimensionStore

logger = logging.getLogger(__name__)

_STORAGE_DIR = Path(".aki/memory/semantic")
_NAMESPACE_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_namespace(ns: str) -> None:
    if not ns or not _NAMESPACE_RE.match(ns):
        raise ValueError(
            f"Invalid namespace {ns!r}: must be non-empty and contain only "
            "alphanumeric characters, dashes, and underscores."
        )


def _parse_md_with_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse a markdown file with optional YAML frontmatter (--- delimited)."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                meta = yaml.safe_load(parts[1]) or {}
                body = parts[2].strip()
                return (meta if isinstance(meta, dict) else {}), body
            except yaml.YAMLError:
                pass
    return {}, text.strip()


def _format_md_with_frontmatter(meta: dict[str, Any], body: str) -> str:
    """Render a markdown file with YAML frontmatter."""
    fm = yaml.dump(
        meta,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).strip()
    return f"---\n{fm}\n---\n\n{body}\n"


def _atomic_text_write(path: Path, content: str) -> None:
    """Write text atomically using tempfile + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


class SemanticMemoryStore(DimensionStore):
    """Markdown-based knowledge store with YAML frontmatter — facts, notes, docs."""

    dimension = "semantic"

    def __init__(self, base_dir: Path | None = None):
        self._dir = base_dir or _STORAGE_DIR

    def _ns_dir(self, namespace: str) -> Path:
        _validate_namespace(namespace)
        return self._dir / namespace

    # ── DimensionStore interface ────────────────────────────────────────

    def load(self, user_id: str) -> dict[str, Any]:
        """Load all entries for a namespace (user_id maps to namespace)."""
        entries = self.list_entries(user_id)
        return {"entries": entries}

    def save(self, user_id: str, data: dict[str, Any]) -> None:
        """Save entries dict. Each key is a name, value has 'meta' and 'body'."""
        entries = data.get("entries", [])
        for entry in entries:
            name = entry.get("name", "")
            body = entry.get("body", "")
            meta = {k: v for k, v in entry.items() if k not in ("name", "body")}
            if name:
                self.write_entry(user_id, name, body, **meta)

    def to_context(self, user_id: str) -> str:
        """Return an index of up to 20 entries for the system prompt."""
        entries = self.list_entries(user_id)
        if not entries:
            return ""
        lines: list[str] = []
        for entry in entries[:20]:
            name = entry.get("name", "?")
            desc = entry.get("description", "")
            tags = entry.get("tags", [])
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            lines.append(f"  - {name}: {desc}{tag_str}")
        return "[Semantic Memory Index:\n" + "\n".join(lines) + "]"

    def update(self, user_id: str, **kwargs: Any) -> None:
        """Update a single entry by name."""
        name = kwargs.pop("name", None)
        if not name:
            raise ValueError("update() requires a 'name' keyword argument.")
        body = kwargs.pop("body", None)
        existing_meta, existing_body = self._read_raw(user_id, name)
        if body is None:
            body = existing_body
        meta = {**existing_meta, **kwargs}
        self.write_entry(user_id, name, body, **meta)

    # ── Semantic-specific API ───────────────────────────────────────────

    def list_entries(self, namespace: str) -> list[dict[str, Any]]:
        """List all .md files in a namespace with their frontmatter."""
        ns_dir = self._ns_dir(namespace)
        if not ns_dir.exists():
            return []
        results: list[dict[str, Any]] = []
        for f in sorted(ns_dir.glob("*.md")):
            try:
                text = f.read_text(encoding="utf-8")
                meta, _ = _parse_md_with_frontmatter(text)
                meta["name"] = f.stem
                results.append(meta)
            except Exception as e:
                logger.warning("Failed to read semantic entry %s: %s", f, e)
        return results

    def read_entry(self, namespace: str, name: str) -> dict[str, Any]:
        """Read full content of a single entry. Returns meta + body."""
        meta, body = self._read_raw(namespace, name)
        return {**meta, "name": name, "body": body}

    def write_entry(
        self,
        namespace: str,
        name: str,
        content: str,
        description: str = "",
        tags: list[str] | None = None,
        **extra_meta: Any,
    ) -> None:
        """Create or update a markdown entry with frontmatter."""
        ns_dir = self._ns_dir(namespace)
        path = ns_dir / f"{name}.md"

        meta: dict[str, Any] = {
            "name": name,
            "description": description,
            "tags": tags or [],
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **extra_meta,
        }

        text = _format_md_with_frontmatter(meta, content)
        _atomic_text_write(path, text)
        logger.debug("Wrote semantic entry %s/%s", namespace, name)

    def search(
        self, namespace: str, query: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Keyword search across all entries in a namespace."""
        query_lower = query.lower()
        ns_dir = self._ns_dir(namespace)
        if not ns_dir.exists():
            return []

        matches: list[dict[str, Any]] = []
        for f in sorted(ns_dir.glob("*.md")):
            try:
                text = f.read_text(encoding="utf-8")
                meta, body = _parse_md_with_frontmatter(text)
                searchable = (
                    f.stem.lower()
                    + " "
                    + meta.get("description", "").lower()
                    + " "
                    + " ".join(t.lower() for t in meta.get("tags", []))
                    + " "
                    + body.lower()
                )
                if query_lower in searchable:
                    meta["name"] = f.stem
                    meta["body"] = body
                    matches.append(meta)
                    if len(matches) >= limit:
                        return matches
            except Exception as e:
                logger.warning("Failed to search semantic entry %s: %s", f, e)

        return matches

    # ── Internal ────────────────────────────────────────────────────────

    def _read_raw(self, namespace: str, name: str) -> tuple[dict[str, Any], str]:
        """Read raw frontmatter + body for an entry. Returns ({}, '') if missing."""
        path = self._ns_dir(namespace) / f"{name}.md"
        if not path.exists():
            return {}, ""
        try:
            text = path.read_text(encoding="utf-8")
            return _parse_md_with_frontmatter(text)
        except Exception as e:
            logger.warning("Failed to read semantic entry %s/%s: %s", namespace, name, e)
            return {}, ""
