"""Tests for the Aki Gateway layer: LaneQueue, SessionPersistence, ContextCompactor."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from aki.gateway.compaction import ContextCompactor
from aki.gateway.lane_queue import LaneQueue
from aki.gateway.persistence import SessionPersistence
from aki.models.base import ModelResponse


# =====================================================================
# LaneQueue
# =====================================================================


@pytest.mark.asyncio
async def test_lane_queue_serialises_same_session():
    """Two concurrent acquires on the same session must run sequentially."""
    queue = LaneQueue()
    order: list[str] = []

    async def worker(label: str):
        async with queue.acquire("sess-1"):
            order.append(f"{label}-start")
            await asyncio.sleep(0.05)
            order.append(f"{label}-end")

    await asyncio.gather(worker("A"), worker("B"))

    # One must fully complete before the other starts
    assert order == ["A-start", "A-end", "B-start", "B-end"] or \
           order == ["B-start", "B-end", "A-start", "A-end"]


@pytest.mark.asyncio
async def test_lane_queue_different_sessions_parallel():
    """Different sessions can run concurrently."""
    queue = LaneQueue()
    order: list[str] = []

    async def worker(session: str, label: str):
        async with queue.acquire(session):
            order.append(f"{label}-start")
            await asyncio.sleep(0.05)
            order.append(f"{label}-end")

    await asyncio.gather(worker("sess-1", "A"), worker("sess-2", "B"))

    # Both should start before either ends (parallel execution)
    assert order[:2] == ["A-start", "B-start"] or order[:2] == ["B-start", "A-start"]


@pytest.mark.asyncio
async def test_lane_queue_pending_count():
    queue = LaneQueue()
    assert queue.pending_count("sess-1") == 0

    acquired = asyncio.Event()
    release = asyncio.Event()

    async def holder():
        async with queue.acquire("sess-1"):
            acquired.set()
            await release.wait()

    task = asyncio.create_task(holder())
    await acquired.wait()
    assert queue.pending_count("sess-1") == 1

    release.set()
    await task
    assert queue.pending_count("sess-1") == 0


@pytest.mark.asyncio
async def test_lane_queue_cleanup():
    queue = LaneQueue()
    async with queue.acquire("sess-1"):
        pass
    queue.cleanup("sess-1")
    assert "sess-1" not in queue._locks


# =====================================================================
# SessionPersistence
# =====================================================================


def test_persistence_register_and_lookup():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = SessionPersistence(base_dir=tmpdir)
        p.load_index()

        assert p.lookup_session("discord", "chan123") is None

        p.register_session(
            session_id="sess-abc",
            platform="discord",
            channel_id="chan123",
            user_id="user456",
        )
        assert p.lookup_session("discord", "chan123") == "sess-abc"

        # Verify persisted to disk
        p2 = SessionPersistence(base_dir=tmpdir)
        p2.load_index()
        assert p2.lookup_session("discord", "chan123") == "sess-abc"


def test_persistence_append_and_load_transcript():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = SessionPersistence(base_dir=tmpdir)

        p.append_entry("sess-1", {"id": "m1", "type": "user", "text": "hello"})
        p.append_entry("sess-1", {"id": "m2", "type": "assistant", "text": "hi there"})

        entries = p.load_transcript("sess-1")
        assert len(entries) == 2
        assert entries[0]["text"] == "hello"
        assert entries[1]["text"] == "hi there"


def test_persistence_rebuild_history():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = SessionPersistence(base_dir=tmpdir)

        p.append_entry("sess-1", {"id": "m1", "type": "user", "text": "hello"})
        p.append_entry("sess-1", {"id": "m2", "type": "assistant", "text": "hi"})
        p.append_entry("sess-1", {"id": "m3", "type": "user", "text": "how are you"})

        history = p.rebuild_history("sess-1")
        assert len(history) == 3
        assert history[0] == {"role": "user", "content": "hello"}
        assert history[1] == {"role": "assistant", "content": "hi"}
        assert history[2] == {"role": "user", "content": "how are you"}


def test_persistence_rebuild_history_with_compaction():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = SessionPersistence(base_dir=tmpdir)

        # Old messages
        p.append_entry("sess-1", {"id": "m1", "type": "user", "text": "msg1"})
        p.append_entry("sess-1", {"id": "m2", "type": "assistant", "text": "reply1"})
        p.append_entry("sess-1", {"id": "m3", "type": "user", "text": "msg2"})
        # Compaction replaces everything above
        p.append_entry("sess-1", {
            "id": "cmp-1",
            "type": "compaction",
            "summary": "User sent msg1 and msg2, got replies.",
            "replaced_count": 3,
        })
        # New messages after compaction
        p.append_entry("sess-1", {"id": "m4", "type": "user", "text": "msg3"})
        p.append_entry("sess-1", {"id": "m5", "type": "assistant", "text": "reply3"})

        history = p.rebuild_history("sess-1")
        assert len(history) == 3
        assert history[0]["role"] == "system"
        assert "summary" in history[0]["content"].lower()
        assert history[1] == {"role": "user", "content": "msg3"}
        assert history[2] == {"role": "assistant", "content": "reply3"}


def test_persistence_empty_transcript():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = SessionPersistence(base_dir=tmpdir)
        assert p.load_transcript("nonexistent") == []
        assert p.rebuild_history("nonexistent") == []


def test_persistence_remove_session():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = SessionPersistence(base_dir=tmpdir)
        p.load_index()
        p.register_session("sess-1", "discord", "chan1", "user1")
        assert p.lookup_session("discord", "chan1") == "sess-1"
        p.remove_session("discord", "chan1")
        assert p.lookup_session("discord", "chan1") is None


# =====================================================================
# ContextCompactor
# =====================================================================


def _make_history(n: int) -> list[dict[str, Any]]:
    """Generate a conversation history with n entries."""
    history = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        # ~100 chars per message → ~25 tokens per message
        history.append({"role": role, "content": f"Message number {i}. " + "x" * 80})
    return history


@pytest.mark.asyncio
async def test_compactor_no_compaction_needed():
    mock_llm = AsyncMock()
    compactor = ContextCompactor(llm=mock_llm, max_context_tokens=8000)

    short_history = _make_history(5)
    result = await compactor.compact(short_history)
    assert result == short_history
    mock_llm.chat.assert_not_called()


@pytest.mark.asyncio
async def test_compactor_triggers_on_threshold():
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = ModelResponse(
        content="Summary of the conversation.",
        model="mock",
    )
    # Low threshold to ensure compaction triggers
    compactor = ContextCompactor(
        llm=mock_llm,
        max_context_tokens=200,
        soft_threshold_ratio=0.5,
        keep_recent=3,
    )

    history = _make_history(20)
    assert compactor.needs_compaction(history)

    result = await compactor.compact(history)

    # Should have: 1 summary + 3 recent = 4 entries
    assert len(result) == 4
    assert result[0]["role"] == "system"
    assert "Summary of the conversation" in result[0]["content"]
    # Recent messages preserved
    assert result[1:] == history[-3:]
    mock_llm.chat.assert_called_once()


@pytest.mark.asyncio
async def test_compactor_records_to_persistence():
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = ModelResponse(
        content="Compressed summary.",
        model="mock",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = SessionPersistence(base_dir=tmpdir)

        compactor = ContextCompactor(
            llm=mock_llm,
            max_context_tokens=200,
            soft_threshold_ratio=0.5,
            keep_recent=3,
        )

        history = _make_history(20)
        await compactor.compact(history, persistence=persistence, session_id="sess-1")

        # Verify compaction entry was written to JSONL
        entries = persistence.load_transcript("sess-1")
        assert len(entries) == 1
        assert entries[0]["type"] == "compaction"
        assert entries[0]["summary"] == "Compressed summary."
        assert entries[0]["replaced_count"] == 17  # 20 - 3 kept


@pytest.mark.asyncio
async def test_compactor_llm_failure_returns_original():
    mock_llm = AsyncMock()
    mock_llm.chat.side_effect = RuntimeError("LLM unavailable")

    compactor = ContextCompactor(
        llm=mock_llm,
        max_context_tokens=200,
        soft_threshold_ratio=0.5,
        keep_recent=3,
    )

    history = _make_history(20)
    result = await compactor.compact(history)

    # On failure, original history is returned unchanged
    assert result == history
