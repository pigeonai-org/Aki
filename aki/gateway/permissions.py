"""
Gateway permission system — per-user access control.

Permission groups:
    owner    Full access. Shell, restart, manage other users' permissions.
    user     Normal chat. Most tools available, dangerous ones blocked.
    blocked  Cannot interact with Aki at all. Messages silently ignored.

Storage: .aki/permissions.yaml

Users not in the file default to "user" group.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_PERMISSIONS_PATH = Path(".aki/permissions.yaml")

# Tools restricted to owner only
OWNER_ONLY_TOOLS = frozenset({
    "shell",
    "system_restart",
    "file_write",
    "file_list",
})

# Tools blocked for all gateway users (override with owner)
# Empty by default — owner_only is the main restriction
BLOCKED_TOOLS: frozenset[str] = frozenset()

VALID_GROUPS = {"owner", "user", "blocked"}


class PermissionManager:
    """Manages per-user permission groups."""

    def __init__(self, path: Path | None = None):
        self._path = path or _PERMISSIONS_PATH
        self._users: dict[str, str] = {}  # user_id → group
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        if self._path.exists():
            try:
                data = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
                self._users = {str(k): str(v) for k, v in data.get("users", {}).items()}
            except Exception as e:
                logger.warning("Failed to load permissions: %s", e)
                self._users = {}
        # Auto-add owner from env or .env file
        owner_id = os.environ.get("AKI_OWNER_ID", "")
        if not owner_id:
            # Try loading from .env via dotenv (pydantic-settings reads .env but os.environ doesn't)
            try:
                from dotenv import dotenv_values
                env = dotenv_values(".env")
                owner_id = env.get("AKI_OWNER_ID", "")
            except ImportError:
                pass
        if owner_id and self._users.get(owner_id) != "owner":
            self._users[owner_id] = "owner"
            self._save()
        self._loaded = True

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {"users": self._users}
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
            os.replace(tmp_path, str(self._path))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def get_group(self, user_id: str) -> str:
        """Return the permission group for a user. Defaults to 'user'."""
        self._ensure_loaded()
        return self._users.get(str(user_id), "user")

    def set_group(self, user_id: str, group: str) -> None:
        """Set a user's permission group."""
        if group not in VALID_GROUPS:
            raise ValueError(f"Invalid group '{group}'. Must be one of: {VALID_GROUPS}")
        self._ensure_loaded()
        self._users[str(user_id)] = group
        self._save()

    def remove_user(self, user_id: str) -> bool:
        """Remove a user from permissions (reverts to default 'user'). Returns True if found."""
        self._ensure_loaded()
        found = str(user_id) in self._users
        self._users.pop(str(user_id), None)
        if found:
            self._save()
        return found

    def list_users(self) -> dict[str, str]:
        """Return all explicitly configured users."""
        self._ensure_loaded()
        return dict(self._users)

    def is_owner(self, user_id: str) -> bool:
        return self.get_group(user_id) == "owner"

    def is_blocked(self, user_id: str) -> bool:
        return self.get_group(user_id) == "blocked"

    def get_blocked_tools(self, user_id: str) -> frozenset[str]:
        """Return tools that should be disabled for this user."""
        group = self.get_group(user_id)
        if group == "owner":
            return frozenset()  # owner can use everything
        if group == "blocked":
            return frozenset({"*"})  # irrelevant — blocked users can't chat
        # Regular user: block dangerous tools
        return OWNER_ONLY_TOOLS | BLOCKED_TOOLS


# Global singleton
_manager: PermissionManager | None = None


def get_permission_manager() -> PermissionManager:
    global _manager
    if _manager is None:
        _manager = PermissionManager()
    return _manager
