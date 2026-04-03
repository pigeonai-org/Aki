"""Episodic memory dimension — what happened in past conversations.

Timeline of session summaries stored as per-day YAML files.

Storage: .aki/memory/episodic/<user_id>/<YYYY-MM-DD>.yaml
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

_STORAGE_DIR = Path(".aki/memory/episodic")
_USER_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_user_id(user_id: str) -> None:
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


class EpisodicMemoryStore(DimensionStore):
    """Timeline of conversation episodes — session summaries, decisions, topics."""

    dimension = "episodic"

    def __init__(self, base_dir: Path | None = None):
        self._dir = base_dir or _STORAGE_DIR

    def _user_dir(self, user_id: str) -> Path:
        _validate_user_id(user_id)
        return self._dir / user_id

    def _today_path(self, user_id: str) -> Path:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._user_dir(user_id) / f"{today}.yaml"

    # ── DimensionStore interface ────────────────────────────────────────

    def load(self, user_id: str) -> dict[str, Any]:
        """Load all episodes for a user, keyed by date."""
        user_dir = self._user_dir(user_id)
        result: dict[str, list[dict[str, Any]]] = {}
        if not user_dir.exists():
            return {"episodes": result}
        for f in sorted(user_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    result[f.stem] = data
            except Exception as e:
                logger.warning("Failed to load episodic file %s: %s", f, e)
        return {"episodes": result}

    def save(self, user_id: str, data: dict[str, Any]) -> None:
        """Save full episodes dict (keyed by date string) for a user."""
        episodes = data.get("episodes", {})
        for date_str, entries in episodes.items():
            path = self._user_dir(user_id) / f"{date_str}.yaml"
            _atomic_yaml_write(path, entries)

    def to_context(self, user_id: str) -> str:
        """Format the most recent 5 episodes as a context block."""
        recent = self.get_recent(user_id, limit=5)
        if not recent:
            return ""
        lines: list[str] = []
        for ep in recent:
            ts = ep.get("timestamp", "?")
            summary = ep.get("summary", "")
            lines.append(f"  - [{ts}] {summary}")
        return "[Recent History:\n" + "\n".join(lines) + "]"

    def update(self, user_id: str, **kwargs: Any) -> None:
        """Convenience: add an episode via keyword arguments."""
        self.add_episode(user_id, **kwargs)

    # ── Episodic-specific API ───────────────────────────────────────────

    def add_episode(
        self,
        user_id: str,
        session_id: str,
        summary: str,
        key_decisions: list[str] | None = None,
        outcome: str = "",
        topics: list[str] | None = None,
        emotional_tone: str = "",
    ) -> None:
        """Append a new episode entry to today's file."""
        path = self._today_path(user_id)

        # Load existing entries for today
        existing: list[dict[str, Any]] = []
        if path.exists():
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    existing = data
            except Exception as e:
                logger.warning("Failed to read today's episodic file, starting fresh: %s", e)

        entry: dict[str, Any] = {
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "key_decisions": key_decisions or [],
            "outcome": outcome,
            "emotional_tone": emotional_tone,
            "topics": topics or [],
        }

        existing.append(entry)
        _atomic_yaml_write(path, existing)
        logger.debug("Added episode for user %s, session %s", user_id, session_id)

    def get_recent(self, user_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Return the most recent *limit* episodes across all day-files."""
        user_dir = self._user_dir(user_id)
        if not user_dir.exists():
            return []

        all_episodes: list[dict[str, Any]] = []
        # Iterate day-files in reverse chronological order
        for f in sorted(user_dir.glob("*.yaml"), reverse=True):
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    # Episodes within a file are in chronological order; reverse them
                    all_episodes.extend(reversed(data))
                    if len(all_episodes) >= limit:
                        break
            except Exception as e:
                logger.warning("Failed to read episodic file %s: %s", f, e)

        return all_episodes[:limit]

    def search(
        self, user_id: str, query: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Keyword search across episode summaries and topics."""
        query_lower = query.lower()
        user_dir = self._user_dir(user_id)
        if not user_dir.exists():
            return []

        matches: list[dict[str, Any]] = []
        for f in sorted(user_dir.glob("*.yaml"), reverse=True):
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8"))
                if not isinstance(data, list):
                    continue
                for ep in data:
                    summary = ep.get("summary", "").lower()
                    topics = [t.lower() for t in ep.get("topics", [])]
                    decisions = [d.lower() for d in ep.get("key_decisions", [])]
                    searchable = summary + " " + " ".join(topics) + " " + " ".join(decisions)
                    if query_lower in searchable:
                        matches.append(ep)
                        if len(matches) >= limit:
                            return matches
            except Exception as e:
                logger.warning("Failed to search episodic file %s: %s", f, e)

        return matches
