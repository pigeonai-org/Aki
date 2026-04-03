"""Session metadata and types."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

@dataclass
class SessionMeta:
    """Metadata for a session, persisted as meta.yaml."""
    session_id: str
    user_id: str = ""
    personality_name: str = ""
    state: str = "active"          # active | dormant | archived
    created_at: str = ""           # ISO 8601
    updated_at: str = ""           # ISO 8601
    message_count: int = 0
    summary: str = ""              # Post-session summary (filled by review pass)
    promoted: bool = False         # Whether review pass has run
    tags: list[str] = field(default_factory=list)

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()
