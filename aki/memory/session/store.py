"""
Session store — persistent per-session memory with on-demand loading.

Each session is a directory under .aki/sessions/<session_id>/:
    messages.jsonl      Full conversation history (role, content, timestamp)
    observations.jsonl  Tool results, intermediate state, agent observations
    shared.json         Inter-agent shared task state
    meta.yaml           Session metadata (user_id, personality, state, etc.)

Lifecycle:
    create → active (memory + disk sync) → dormant (disk only) → resume/archive
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from aki.memory.session.types import SessionMeta

logger = logging.getLogger(__name__)

_BASE_DIR = Path(".aki/sessions")


@dataclass
class Session:
    """An active or loaded session with buffered messages and observations."""
    meta: SessionMeta
    messages: list[dict[str, Any]] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    shared: dict[str, Any] = field(default_factory=dict)

    @property
    def session_id(self) -> str:
        return self.meta.session_id

    @property
    def is_active(self) -> bool:
        return self.meta.state == "active"


class SessionStore:
    """Manages session persistence and lifecycle."""

    def __init__(self, base_dir: Path | None = None):
        self._base_dir = base_dir or _BASE_DIR
        self._active: dict[str, Session] = {}  # session_id → Session (in-memory)

    def _session_dir(self, session_id: str) -> Path:
        # Validate session_id to prevent path traversal
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', session_id):
            raise ValueError(f"Invalid session_id: {session_id}")
        return self._base_dir / session_id

    # ── Create ──

    def create(
        self,
        user_id: str = "",
        personality_name: str = "",
        session_id: str | None = None,
        tags: list[str] | None = None,
    ) -> Session:
        """Create a new session and return it in active state."""
        sid = session_id or uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()

        meta = SessionMeta(
            session_id=sid,
            user_id=user_id,
            personality_name=personality_name,
            state="active",
            created_at=now,
            updated_at=now,
            tags=tags or [],
        )

        session = Session(meta=meta)

        # Create directory and persist meta
        session_dir = self._session_dir(sid)
        session_dir.mkdir(parents=True, exist_ok=True)
        self._save_meta(session)

        # Track as active
        self._active[sid] = session
        logger.info("Created session %s", sid)
        return session

    # ── Get / Resume ──

    def get(self, session_id: str) -> Session | None:
        """Get an active session, or None if not active."""
        return self._active.get(session_id)

    def resume(self, session_id: str) -> Session | None:
        """Load a dormant session from disk into active state."""
        # Already active?
        if session_id in self._active:
            return self._active[session_id]

        session_dir = self._session_dir(session_id)
        if not session_dir.is_dir():
            logger.warning("Session directory not found: %s", session_dir)
            return None

        # Load meta
        meta = self._load_meta(session_id)
        if meta is None:
            return None

        session = Session(meta=meta)

        # Load messages
        messages_path = session_dir / "messages.jsonl"
        if messages_path.exists():
            session.messages = self._read_jsonl(messages_path)

        # Load observations
        obs_path = session_dir / "observations.jsonl"
        if obs_path.exists():
            session.observations = self._read_jsonl(obs_path)

        # Load shared state
        shared_path = session_dir / "shared.json"
        if shared_path.exists():
            try:
                session.shared = json.loads(shared_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                session.shared = {}

        # Mark active
        session.meta.state = "active"
        session.meta.touch()
        self._save_meta(session)
        self._active[session_id] = session

        logger.info("Resumed session %s (%d messages)", session_id, len(session.messages))
        return session

    # ── Write operations ──

    def append_message(self, session_id: str, role: str, content: str, **extra: Any) -> None:
        """Append a message to an active session (memory + disk)."""
        session = self._active.get(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} is not active")

        entry = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **extra,
        }
        session.messages.append(entry)
        session.meta.message_count = len(session.messages)
        session.meta.touch()

        # Append to disk
        messages_path = self._session_dir(session_id) / "messages.jsonl"
        self._append_jsonl(messages_path, entry)

    def append_observation(self, session_id: str, observation: dict[str, Any]) -> None:
        """Append an observation (tool result, etc.) to an active session."""
        session = self._active.get(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} is not active")

        observation.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        session.observations.append(observation)
        session.meta.touch()

        obs_path = self._session_dir(session_id) / "observations.jsonl"
        self._append_jsonl(obs_path, observation)

    def update_shared(self, session_id: str, key: str, value: Any) -> None:
        """Update shared inter-agent state."""
        session = self._active.get(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} is not active")

        session.shared[key] = value
        shared_path = self._session_dir(session_id) / "shared.json"
        shared_path.write_text(
            json.dumps(session.shared, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    # ── Lifecycle ──

    def suspend(self, session_id: str) -> None:
        """Move an active session to dormant state (free memory, keep disk)."""
        session = self._active.pop(session_id, None)
        if session is None:
            return

        session.meta.state = "dormant"
        session.meta.touch()
        self._save_meta(session)
        logger.info("Suspended session %s", session_id)

    def archive(self, session_id: str, summary: str = "") -> None:
        """Mark a session as archived after review pass."""
        session = self._active.pop(session_id, None)
        if session is None:
            # Load meta from disk
            meta = self._load_meta(session_id)
            if meta is None:
                return
            session = Session(meta=meta)

        session.meta.state = "archived"
        session.meta.summary = summary
        session.meta.promoted = True
        session.meta.touch()
        self._save_meta(session)
        logger.info("Archived session %s", session_id)

    # ── List / Discovery ──

    def list_sessions(
        self,
        state: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> list[SessionMeta]:
        """List sessions, optionally filtered by state and/or user_id."""
        if not self._base_dir.exists():
            return []

        results: list[SessionMeta] = []
        for entry in sorted(self._base_dir.iterdir(), reverse=True):
            if not entry.is_dir():
                continue
            meta = self._load_meta(entry.name)
            if meta is None:
                continue
            if state and meta.state != state:
                continue
            if user_id and meta.user_id != user_id:
                continue
            results.append(meta)
            if len(results) >= limit:
                break

        # Sort by updated_at DESC
        results.sort(key=lambda m: m.updated_at or "", reverse=True)
        return results[:limit]

    def get_active_sessions(self) -> list[Session]:
        """Return all currently active (in-memory) sessions."""
        return list(self._active.values())

    # ── Persistence helpers ──

    def _save_meta(self, session: Session) -> None:
        meta_path = self._session_dir(session.session_id) / "meta.yaml"
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "session_id": session.meta.session_id,
            "user_id": session.meta.user_id,
            "personality_name": session.meta.personality_name,
            "state": session.meta.state,
            "created_at": session.meta.created_at,
            "updated_at": session.meta.updated_at,
            "message_count": session.meta.message_count,
            "summary": session.meta.summary,
            "promoted": session.meta.promoted,
            "tags": session.meta.tags,
        }
        meta_path.write_text(
            yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

    def _load_meta(self, session_id: str) -> SessionMeta | None:
        meta_path = self._session_dir(session_id) / "meta.yaml"
        if not meta_path.exists():
            return None
        try:
            data = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
            return SessionMeta(**{k: v for k, v in data.items() if hasattr(SessionMeta, k)})
        except Exception as e:
            logger.warning("Failed to load meta for session %s: %s", session_id, e)
            return None

    def _append_jsonl(self, path: Path, entry: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

    def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            results.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except OSError:
            pass
        return results


# ── Global singleton ──

_store: SessionStore | None = None

def get_session_store() -> SessionStore:
    global _store
    if _store is None:
        _store = SessionStore()
    return _store

def reset_session_store() -> None:
    global _store
    _store = None
