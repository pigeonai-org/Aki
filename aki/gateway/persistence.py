"""JSONL session persistence and sessions index.

Storage layout::

    .aki/sessions/
    ├── sessions.json            # platform:channel → session metadata
    └── {session_id}.jsonl       # append-only transcript per session

``sessions.json`` is a small mutable index.  Each ``.jsonl`` file is
append-only — messages, tool calls, and compaction entries are appended
as one JSON object per line.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _safe_session_id(session_id: str) -> str:
    if not re.match(r'^[a-zA-Z0-9_-]+$', session_id):
        raise ValueError(f"Invalid session_id: contains unsafe characters")
    return session_id


class SessionPersistence:
    """Manages JSONL transcripts and the sessions index file."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        self._base = Path(base_dir) if base_dir else Path(".aki/sessions")
        self._index: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Index operations
    # ------------------------------------------------------------------

    def load_index(self) -> dict[str, dict[str, Any]]:
        """Load ``sessions.json`` from disk.  Returns the loaded dict."""
        index_path = self._base / "sessions.json"
        if index_path.exists():
            try:
                self._index = json.loads(index_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._index = {}
        else:
            self._index = {}
        return self._index

    def save_index(self) -> None:
        """Persist the in-memory index to ``sessions.json``."""
        self._base.mkdir(parents=True, exist_ok=True)
        index_path = self._base / "sessions.json"
        index_path.write_text(
            json.dumps(self._index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def lookup_session(self, platform: str, channel_id: str) -> str | None:
        """Return ``session_id`` for a *platform:channel_id* key, or ``None``."""
        key = f"{platform}:{channel_id}"
        entry = self._index.get(key)
        return entry["session_id"] if entry else None

    def register_session(
        self,
        session_id: str,
        platform: str,
        channel_id: str,
        user_id: str,
        llm_config: str = "openai:gpt-4o",
    ) -> None:
        """Create an index entry for a new session and flush to disk."""
        key = f"{platform}:{channel_id}"
        now = datetime.now(timezone.utc).isoformat()
        self._index[key] = {
            "session_id": session_id,
            "platform": platform,
            "channel_id": channel_id,
            "user_id": user_id,
            "llm_config": llm_config,
            "created_at": now,
            "updated_at": now,
        }
        self.save_index()

    def touch_session(self, platform: str, channel_id: str) -> None:
        """Update the ``updated_at`` timestamp for an existing entry."""
        key = f"{platform}:{channel_id}"
        if key in self._index:
            self._index[key]["updated_at"] = datetime.now(timezone.utc).isoformat()
            self.save_index()

    def remove_session(self, platform: str, channel_id: str) -> None:
        """Remove a session from the index (transcript file is kept)."""
        key = f"{platform}:{channel_id}"
        self._index.pop(key, None)
        self.save_index()

    # ------------------------------------------------------------------
    # Transcript operations
    # ------------------------------------------------------------------

    def _transcript_path(self, session_id: str) -> Path:
        session_id = _safe_session_id(session_id)
        return self._base / f"{session_id}.jsonl"

    def append_entry(self, session_id: str, entry: dict[str, Any]) -> None:
        """Append one JSON line to the session transcript."""
        self._base.mkdir(parents=True, exist_ok=True)
        path = self._transcript_path(session_id)
        line = json.dumps(entry, ensure_ascii=False, default=str)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def load_transcript(self, session_id: str) -> list[dict[str, Any]]:
        """Read all entries from a session transcript."""
        path = self._transcript_path(session_id)
        if not path.exists():
            return []
        entries: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return entries

    def rebuild_history(self, session_id: str) -> list[dict[str, Any]]:
        """Rebuild ``conversation_history`` from the JSONL transcript.

        Applies compaction entries: when a ``compaction`` entry is found,
        all prior ``user``/``assistant`` messages are replaced by the
        summary.  Returns a list of ``{role, content}`` dicts suitable
        for ``SessionManager``.
        """
        entries = self.load_transcript(session_id)
        if not entries:
            return []

        history: list[dict[str, Any]] = []
        for entry in entries:
            entry_type = entry.get("type", "")

            if entry_type == "compaction":
                # Replace everything accumulated so far with the summary
                summary = entry.get("summary", "")
                history = [{"role": "system", "content": f"[Conversation summary]: {summary}"}]

            elif entry_type == "user":
                text = entry.get("text", "")
                # Include display name so agent can distinguish speakers
                name = entry.get("display_name") or entry.get("user_id", "")
                if name and not text.startswith("["):
                    text = f"[{name}]: {text}"
                history.append({"role": "user", "content": text})

            elif entry_type == "assistant":
                history.append({"role": "assistant", "content": entry.get("text", "")})

            # Other entry types (tool_call, etc.) are skipped for history
            # reconstruction — they are preserved in the JSONL for auditing.

        return history

    def list_sessions(self) -> dict[str, dict[str, Any]]:
        """Return the full index (defensive copy)."""
        return dict(self._index)
