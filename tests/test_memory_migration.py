"""Tests for legacy memory migration utilities."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from aki.memory import MemoryCategory, MemoryManager, migrate_legacy_json_to_long_term
from aki.memory.base import MemoryStore


class InMemoryLongTermStore(MemoryStore):
    """Minimal long-term store for migration tests."""

    def __init__(self) -> None:
        self.items = []

    async def add(self, item):
        self.items.append(item)

    async def get_recent(self, n: int):
        return list(reversed(self.items[-n:]))

    async def search(self, query: str, limit: int = 10):
        query_lower = query.lower()
        matched = [item for item in self.items if query_lower in item.content.lower()]
        return matched[:limit]

    async def search_semantic(self, query):
        return await self.search(query.query or "", query.limit)

    async def get_by_task(self, task_id: str):
        return [item for item in self.items if item.task_id == task_id]

    async def clear(self):
        self.items.clear()

    async def count(self):
        return len(self.items)


@pytest.mark.asyncio
async def test_migrate_legacy_json_dry_run(tmp_path: Path) -> None:
    source = tmp_path / "legacy_memories.json"
    source.write_text(
        json.dumps(
            [
                {
                    "content": "User prefers concise translations.",
                    "type": "user_instruction",
                    "timestamp": datetime.now().isoformat(),
                    "metadata": {"instruction_key": "style"},
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    manager = MemoryManager(long_term=InMemoryLongTermStore())
    stats = await migrate_legacy_json_to_long_term(manager, str(source), dry_run=True)

    assert stats["loaded"] == 1
    assert stats["migrated"] == 1
    assert await manager.recall_long_term(query="concise") == []


@pytest.mark.asyncio
async def test_migrate_legacy_json_classification(tmp_path: Path) -> None:
    source = tmp_path / "legacy_memories.json"
    source.write_text(
        json.dumps(
            [
                {
                    "content": "Official subtitle rulebook excerpt",
                    "type": "domain",
                    "timestamp": datetime.now().isoformat(),
                    "metadata": {},
                },
                {
                    "content": "News update about subtitle standards",
                    "type": "result",
                    "timestamp": datetime.now().isoformat(),
                    "metadata": {"tool": "web_search", "url": "https://example.com/news"},
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    manager = MemoryManager(long_term=InMemoryLongTermStore())
    stats = await migrate_legacy_json_to_long_term(manager, str(source))
    items = await manager.recall_long_term(query="subtitle", limit=10, include_expired=True)

    assert stats["migrated"] == 2
    assert any(item.category == MemoryCategory.DOMAIN_KNOWLEDGE for item in items)
    assert any(item.category == MemoryCategory.WEB_KNOWLEDGE for item in items)
