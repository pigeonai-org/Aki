"""Unit tests for the long-term memory tools and index helper."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import yaml

from aki.tools.memory.memory import (
    MemoryListTool,
    MemoryReadTool,
    MemoryWriteTool,
    _parse_frontmatter,
)
from aki.tools.memory.index import get_memory_index


@pytest.fixture()
def memory_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the memory directory to a temp folder."""
    mem_dir = tmp_path / "long-term-memory"
    mem_dir.mkdir()
    monkeypatch.setattr(
        "aki.tools.memory.memory._memory_dir",
        lambda: mem_dir,
    )
    monkeypatch.setattr(
        "aki.config.settings.get_settings",
        lambda: _fake_settings(str(mem_dir)),
    )
    return mem_dir


class _FakeMemorySettings:
    def __init__(self, d: str) -> None:
        self.long_term_memory_dir = d
        self.memory_review_enabled = True


class _FakeSettings:
    def __init__(self, d: str) -> None:
        self.memory = _FakeMemorySettings(d)


def _fake_settings(d: str):
    return _FakeSettings(d)


# ---------------------------------------------------------------------------
# _parse_frontmatter
# ---------------------------------------------------------------------------


def test_parse_frontmatter_valid():
    text = "---\nname: test\ndescription: hello\n---\n\nBody here."
    meta, body = _parse_frontmatter(text)
    assert meta["name"] == "test"
    assert meta["description"] == "hello"
    assert "Body here." in body


def test_parse_frontmatter_no_frontmatter():
    text = "Just some plain text."
    meta, body = _parse_frontmatter(text)
    assert meta == {}
    assert body == text


def test_parse_frontmatter_invalid_yaml():
    text = "---\n: : :\n---\nBody"
    meta, body = _parse_frontmatter(text)
    # Should gracefully return empty dict or parsed result, not crash
    assert isinstance(meta, dict)


# ---------------------------------------------------------------------------
# MemoryWriteTool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_write_creates_file(memory_dir: Path):
    tool = MemoryWriteTool()
    result = await tool.execute(
        memory_name="user-profile",
        description="Core user identity info",
        body="## Name\n- Alice\n\n## Age\n- 28",
        type="profile",
        tags="identity, basics",
    )
    assert result.success
    assert result.data["action"] == "created"
    assert result.data["filename"] == "user-profile.md"

    # Verify file content
    path = memory_dir / "user-profile.md"
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert content.startswith("---\n")
    meta, body = _parse_frontmatter(content)
    assert meta["name"] == "user-profile"
    assert meta["description"] == "Core user identity info"
    assert meta["type"] == "profile"
    assert "updated_at" in meta
    assert meta["tags"] == ["identity", "basics"]
    assert "Alice" in body


@pytest.mark.asyncio
async def test_memory_write_updates_existing(memory_dir: Path):
    tool = MemoryWriteTool()
    # Create
    await tool.execute(
        memory_name="interests",
        description="Hobbies v1",
        body="- hiking",
    )
    # Update
    result = await tool.execute(
        memory_name="interests",
        description="Hobbies v2",
        body="- hiking\n- cooking",
    )
    assert result.success
    assert result.data["action"] == "updated"

    content = (memory_dir / "interests.md").read_text(encoding="utf-8")
    assert "cooking" in content


@pytest.mark.asyncio
async def test_memory_write_creates_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    nested = tmp_path / "a" / "b" / "c"
    monkeypatch.setattr(
        "aki.tools.memory.memory._memory_dir",
        lambda: nested,
    )
    tool = MemoryWriteTool()
    result = await tool.execute(
        memory_name="test",
        description="Test memory",
        body="content",
    )
    assert result.success
    assert nested.exists()


# ---------------------------------------------------------------------------
# MemoryReadTool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_read_success(memory_dir: Path):
    # Write a file first
    write_tool = MemoryWriteTool()
    await write_tool.execute(
        memory_name="prefs",
        description="Preferences",
        body="## Food\n- Sushi\n- Italian",
        type="preferences",
        tags="food",
    )

    read_tool = MemoryReadTool()
    result = await read_tool.execute(memory_name="prefs")
    assert result.success
    assert result.data["name"] == "prefs"
    assert result.data["description"] == "Preferences"
    assert result.data["type"] == "preferences"
    assert result.data["tags"] == ["food"]
    assert "Sushi" in result.data["body"]


@pytest.mark.asyncio
async def test_memory_read_not_found(memory_dir: Path):
    tool = MemoryReadTool()
    result = await tool.execute(memory_name="nonexistent")
    assert not result.success
    assert "not found" in result.error


# ---------------------------------------------------------------------------
# MemoryListTool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_list_empty(memory_dir: Path):
    tool = MemoryListTool()
    result = await tool.execute()
    assert result.success
    assert result.data["count"] == 0
    assert result.data["memories"] == []


@pytest.mark.asyncio
async def test_memory_list_returns_entries(memory_dir: Path):
    write_tool = MemoryWriteTool()
    await write_tool.execute(
        memory_name="alpha",
        description="First memory",
        body="content a",
    )
    await write_tool.execute(
        memory_name="beta",
        description="Second memory",
        body="content b",
    )

    list_tool = MemoryListTool()
    result = await list_tool.execute()
    assert result.success
    assert result.data["count"] == 2
    names = {m["name"] for m in result.data["memories"]}
    assert names == {"alpha", "beta"}


@pytest.mark.asyncio
async def test_memory_list_nonexistent_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "aki.tools.memory.memory._memory_dir",
        lambda: tmp_path / "does-not-exist",
    )
    tool = MemoryListTool()
    result = await tool.execute()
    assert result.success
    assert result.data["count"] == 0


# ---------------------------------------------------------------------------
# get_memory_index
# ---------------------------------------------------------------------------


def test_get_memory_index_returns_capped(memory_dir: Path):
    # Create 25 memory files
    for i in range(25):
        (memory_dir / f"mem-{i:02d}.md").write_text(
            f"---\nname: mem-{i:02d}\ndescription: Memory {i}\nupdated_at: 2026-01-{i+1:02d}\n---\n\nBody {i}\n",
            encoding="utf-8",
        )

    index = get_memory_index(limit=20)
    assert len(index) == 20
    # Should be sorted by updated_at descending
    assert index[0]["name"] == "mem-24"


def test_get_memory_index_empty(memory_dir: Path):
    index = get_memory_index()
    assert index == []


# ---------------------------------------------------------------------------
# Unicode handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_write_unicode(memory_dir: Path):
    tool = MemoryWriteTool()
    result = await tool.execute(
        memory_name="chinese-profile",
        description="中文用户画像",
        body="## 姓名\n- 从美玲\n\n## 兴趣\n- 远足\n- 咖啡",
        type="profile",
    )
    assert result.success

    read_tool = MemoryReadTool()
    read_result = await read_tool.execute(memory_name="chinese-profile")
    assert read_result.success
    assert "从美玲" in read_result.data["body"]
    assert read_result.data["description"] == "中文用户画像"
