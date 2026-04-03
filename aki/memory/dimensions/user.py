"""User memory dimension — who the user is. Structured YAML profile.

Storage: .aki/memory/user/<user_id>.yaml
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

_STORAGE_DIR = Path(".aki/memory/user")
_USER_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_user_id(user_id: str) -> None:
    """Raise ValueError if user_id contains invalid characters."""
    if not user_id or not _USER_ID_RE.match(user_id):
        raise ValueError(
            f"Invalid user_id {user_id!r}: must be non-empty and contain only "
            "alphanumeric characters, dashes, and underscores."
        )


def _atomic_yaml_write(path: Path, data: Any) -> None:
    """Write YAML data atomically using tempfile + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            yaml.dump(
                data, f,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            )
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


class UserMemoryStore(DimensionStore):
    """Structured profile of who the user is — name, background, preferences, facts."""

    dimension = "user"

    def __init__(self, base_dir: Path | None = None):
        self._dir = base_dir or _STORAGE_DIR

    def _path(self, user_id: str) -> Path:
        _validate_user_id(user_id)
        return self._dir / f"{user_id}.yaml"

    # ── DimensionStore interface ────────────────────────────────────────

    def load(self, user_id: str) -> dict[str, Any]:
        """Load user profile from YAML. Returns empty dict if no file exists."""
        path = self._path(user_id)
        if not path.exists():
            return {}
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning("Failed to load user profile for %s: %s", user_id, e)
            return {}

    def save(self, user_id: str, data: dict[str, Any]) -> None:
        """Persist full user profile dict to YAML (atomic write)."""
        _validate_user_id(user_id)
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        _atomic_yaml_write(self._path(user_id), data)

    def to_context(self, user_id: str) -> str:
        """Format user profile as a bracketed context block for the system prompt."""
        data = self.load(user_id)
        if not data:
            return ""

        parts: list[str] = []
        if name := data.get("name") or data.get("display_name"):
            parts.append(f"Name: {name}")
        if bg := data.get("background"):
            parts.append(f"Background: {bg}")
        if lang := data.get("language"):
            parts.append(f"Language: {lang}")
        if style := data.get("communication_style"):
            parts.append(f"Style: {style}")
        if prefs := data.get("preferences"):
            parts.append("Preferences: " + "; ".join(str(p) for p in prefs))
        if facts := data.get("facts"):
            parts.append("Facts: " + "; ".join(str(f) for f in facts))

        if not parts:
            return ""
        return "[User Profile: " + ", ".join(parts) + "]"

    def update(self, user_id: str, **kwargs: Any) -> None:
        """Merge kwargs into existing profile and save."""
        data = self.load(user_id)
        data.update(kwargs)
        self.save(user_id, data)

    # ── Convenience helpers ─────────────────────────────────────────────

    def add_fact(self, user_id: str, fact: str) -> None:
        """Append a fact to the user's facts list, deduplicating."""
        data = self.load(user_id)
        facts: list[str] = data.get("facts", [])
        if fact not in facts:
            facts.append(fact)
            data["facts"] = facts
            self.save(user_id, data)
            logger.debug("Added fact for user %s: %s", user_id, fact)

    def set_field(self, user_id: str, key: str, value: Any) -> None:
        """Update a single top-level field in the profile."""
        data = self.load(user_id)
        data[key] = value
        self.save(user_id, data)
