"""Procedural memory dimension — how the user likes things done.

Key-value rules with confidence scores, stored as YAML.

Storage: .aki/memory/procedural/<user_id>.yaml
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

_STORAGE_DIR = Path(".aki/memory/procedural")
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


class ProceduralMemoryStore(DimensionStore):
    """Rules and preferences for how the user likes things done."""

    dimension = "procedural"

    def __init__(self, base_dir: Path | None = None):
        self._dir = base_dir or _STORAGE_DIR

    def _path(self, user_id: str) -> Path:
        _validate_user_id(user_id)
        return self._dir / f"{user_id}.yaml"

    # ── DimensionStore interface ────────────────────────────────────────

    def load(self, user_id: str) -> dict[str, Any]:
        """Load procedural rules from YAML."""
        path = self._path(user_id)
        if not path.exists():
            return {"rules": [], "updated_at": ""}
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
            return {"rules": [], "updated_at": ""}
        except Exception as e:
            logger.warning("Failed to load procedural memory for %s: %s", user_id, e)
            return {"rules": [], "updated_at": ""}

    def save(self, user_id: str, data: dict[str, Any]) -> None:
        """Persist full procedural memory dict to YAML."""
        _validate_user_id(user_id)
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        _atomic_yaml_write(self._path(user_id), data)

    def to_context(self, user_id: str) -> str:
        """Format rules as a bracketed context block for the system prompt."""
        rules = self.get_rules(user_id, min_confidence=0.0)
        if not rules:
            return ""
        rule_texts = [r["rule"] for r in rules]
        return "[Work Preferences: " + "; ".join(rule_texts) + "]"

    def update(self, user_id: str, **kwargs: Any) -> None:
        """Convenience: add a rule via keyword arguments."""
        rule = kwargs.get("rule")
        if rule:
            self.add_rule(
                user_id,
                rule=rule,
                confidence=kwargs.get("confidence", 0.5),
                source=kwargs.get("source", ""),
            )

    # ── Procedural-specific API ─────────────────────────────────────────

    def add_rule(
        self,
        user_id: str,
        rule: str,
        confidence: float = 0.5,
        source: str = "",
    ) -> None:
        """Append a rule, deduplicating by rule text. Updates existing if found."""
        data = self.load(user_id)
        rules: list[dict[str, Any]] = data.get("rules", [])

        # Deduplicate: if the same rule text exists, update it
        for existing in rules:
            if existing.get("rule", "").strip().lower() == rule.strip().lower():
                existing["confidence"] = confidence
                existing["source"] = source
                existing["added"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                logger.debug("Updated existing rule for user %s: %s", user_id, rule)
                data["rules"] = rules
                self.save(user_id, data)
                return

        rules.append({
            "rule": rule,
            "confidence": confidence,
            "source": source,
            "added": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        })
        data["rules"] = rules
        self.save(user_id, data)
        logger.debug("Added rule for user %s: %s", user_id, rule)

    def remove_rule(self, user_id: str, rule: str) -> bool:
        """Remove a rule by its text. Returns True if found and removed."""
        data = self.load(user_id)
        rules: list[dict[str, Any]] = data.get("rules", [])
        original_len = len(rules)
        rules = [r for r in rules if r.get("rule", "").strip().lower() != rule.strip().lower()]
        if len(rules) == original_len:
            return False
        data["rules"] = rules
        self.save(user_id, data)
        logger.debug("Removed rule for user %s: %s", user_id, rule)
        return True

    def get_rules(
        self, user_id: str, min_confidence: float = 0.0
    ) -> list[dict[str, Any]]:
        """Return rules filtered by minimum confidence threshold."""
        data = self.load(user_id)
        rules: list[dict[str, Any]] = data.get("rules", [])
        if min_confidence > 0.0:
            rules = [r for r in rules if r.get("confidence", 0.0) >= min_confidence]
        return rules
