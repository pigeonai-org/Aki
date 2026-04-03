"""Tests for upgraded short-term/long-term memory behavior."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

import pytest

from aki.agent import AgentContext, UniversalAgent
from aki.agent.roles import Role
from aki.memory import MemoryItem, MemoryManager
from aki.memory.base import MemoryStore
from aki.memory.stores.short_term import ShortTermMemoryStore
from aki.memory.types import MemoryCategory, MemoryQuery, MemoryScope
from aki.tools import BaseTool, ToolParameter, ToolResult


class InMemorySemanticLongTermStore(MemoryStore):
    """Test double with keyword-based semantic retrieval and dedupe."""

    def __init__(self) -> None:
        self._items: list[MemoryItem] = []

    async def add(self, item: MemoryItem) -> None:
        if item.fingerprint:
            self._items = [
                memory
                for memory in self._items
                if not (
                    memory.fingerprint == item.fingerprint
                    and memory.namespace == item.namespace
                    and memory.category == item.category
                )
            ]
        self._items.append(item)

    async def get_recent(self, n: int) -> list[MemoryItem]:
        return sorted(self._items, key=lambda item: item.timestamp, reverse=True)[:n]

    async def search(self, query: str, limit: int = 10) -> list[MemoryItem]:
        query_lower = query.lower()
        filtered = [item for item in self._items if query_lower in item.content.lower()]
        return sorted(filtered, key=lambda item: item.timestamp, reverse=True)[:limit]

    async def search_semantic(self, query: MemoryQuery) -> list[MemoryItem]:
        candidates = await self.search(query.query or "", limit=max(1, query.limit * 2))
        now = query.now or datetime.now()
        results: list[MemoryItem] = []
        for item in candidates:
            if item.namespace != query.namespace:
                continue
            if query.categories and item.category not in query.categories:
                continue
            if query.task_id and item.task_id != query.task_id:
                continue
            if not query.include_expired and item.expires_at and item.expires_at <= now:
                continue
            results.append(item)
            if len(results) >= query.limit:
                break
        return results

    async def get_by_task(self, task_id: str) -> list[MemoryItem]:
        return [item for item in self._items if item.task_id == task_id]

    async def clear(self) -> None:
        self._items.clear()

    async def count(self) -> int:
        return len(self._items)

    async def prune_expired(self, now: Optional[datetime] = None) -> int:
        cutoff = now or datetime.now()
        before = len(self._items)
        self._items = [
            item for item in self._items if not (item.expires_at and item.expires_at <= cutoff)
        ]
        return before - len(self._items)


class MockLLM:
    """Small chat stub used by agent tests. Accepts ModelResponse objects."""

    def __init__(self, responses: Optional[list[Any]] = None) -> None:
        from aki.models.base import ModelResponse
        self.responses: list[Any] = responses or [ModelResponse(content="done", model="mock", metadata={})]
        self.calls = 0

    async def chat(self, messages, **kwargs):  # noqa: ANN001
        del messages, kwargs
        response = (
            self.responses[self.calls] if self.calls < len(self.responses) else self.responses[-1]
        )
        self.calls += 1
        return response


class WebSearchTool(BaseTool):
    """Tool emitting web_search-shaped output for ingestion checks."""

    name = "web_search"
    description = "search web"
    parameters = [
        ToolParameter(name="query", type="string", description="query"),
    ]

    async def execute(self, query: str, **kwargs) -> ToolResult:
        del kwargs
        return ToolResult.ok(
            data={
                "query": query,
                "results": [
                    {
                        "title": "Persistent style guide",
                        "url": "https://example.com/style-guide",
                        "content": "Use concise imperative instructions for subtitle edits.",
                    }
                ],
            }
        )


def _build_test_role() -> Role:
    return Role(
        name="web_ingest",
        persona="Invokes web search tool once for memory ingestion checks",
        system_prompt="test",
        allowed_tools=["web_search"],
    )


@pytest.mark.asyncio
async def test_short_term_task_isolation() -> None:
    manager = MemoryManager(
        short_term=ShortTermMemoryStore(max_size=50, max_items_per_task=10),
        long_term=None,
    )

    await manager.remember_short_term(
        content="memory for task A", type="observation", task_id="task-a"
    )
    await manager.remember_short_term(
        content="memory for task B", type="observation", task_id="task-b"
    )

    task_a_memories = await manager.recall_short_term(task_id="task-a", limit=10)
    assert task_a_memories
    assert all(item.task_id == "task-a" for item in task_a_memories)
    assert not any("task B" in item.content for item in task_a_memories)


@pytest.mark.asyncio
async def test_long_term_user_instruction_upsert() -> None:
    long_term = InMemorySemanticLongTermStore()
    manager = MemoryManager(long_term=long_term)

    await manager.upsert_user_instruction(key="tone", content="Use concise style.")
    await manager.upsert_user_instruction(key="tone", content="Use very concise style.")

    instructions = await manager.recall_long_term(
        query="concise",
        categories={MemoryCategory.USER_INSTRUCTION},
        include_expired=True,
    )

    assert len(instructions) == 1
    assert instructions[0].category == MemoryCategory.USER_INSTRUCTION
    assert "very concise" in instructions[0].content


@pytest.mark.asyncio
async def test_web_knowledge_ttl_and_prune() -> None:
    long_term = InMemorySemanticLongTermStore()
    manager = MemoryManager(long_term=long_term, web_ttl_days=30)

    await manager.remember_long_term(
        content="Old web note",
        category=MemoryCategory.WEB_KNOWLEDGE,
        expires_at=datetime.now() - timedelta(days=1),
    )

    visible = await manager.recall_long_term(
        query="web note",
        categories={MemoryCategory.WEB_KNOWLEDGE},
    )
    assert visible == []

    all_items = await manager.recall_long_term(
        query="web note",
        categories={MemoryCategory.WEB_KNOWLEDGE},
        include_expired=True,
    )
    assert len(all_items) == 1

    removed = await manager.prune_long_term()
    assert removed == 1


@pytest.mark.asyncio
async def test_recall_context_fuses_short_and_long_term() -> None:
    long_term = InMemorySemanticLongTermStore()
    manager = MemoryManager(long_term=long_term)

    await manager.remember_short_term(
        content="current task uses informal spoken subtitles",
        type="observation",
        task_id="task-1",
    )
    await manager.remember_long_term(
        content="Domain rule: preserve speaker intent while shortening lines.",
        category=MemoryCategory.DOMAIN_KNOWLEDGE,
    )

    context = await manager.recall_context(task_id="task-1", query="preserve speaker intent")
    assert context["short_term"]
    assert any(item.scope == MemoryScope.LONG_TERM for item in context["long_term"])


@pytest.mark.asyncio
async def test_web_tool_output_is_ingested_to_long_term_memory() -> None:
    from aki.models.base import ModelResponse, ToolCall

    long_term = InMemorySemanticLongTermStore()
    manager = MemoryManager(long_term=long_term)
    mock_llm = MockLLM(
        responses=[
            ModelResponse(
                content="",
                model="mock",
                metadata={},
                tool_calls=[ToolCall(id="c1", name="web_search", input={"query": "subtitle style guide"})],
            ),
            ModelResponse(content="done", model="mock", metadata={}),
        ]
    )

    agent = UniversalAgent(
        role=_build_test_role(),
        context=AgentContext(),
        llm=mock_llm,
        memory=manager,
        tools=[WebSearchTool()],
    )

    await agent.run("find style guidance")
    memories = await manager.recall_long_term(
        query="subtitle edits",
        categories={MemoryCategory.WEB_KNOWLEDGE},
        include_expired=True,
    )

    assert memories
    assert any("concise imperative instructions" in item.content.lower() for item in memories)


@pytest.mark.asyncio
async def test_tool_result_is_persisted_in_short_term_memory() -> None:
    """After a tool call the result should appear in short-term memory."""
    from aki.models.base import ModelResponse, ToolCall

    manager = MemoryManager()
    mock_llm = MockLLM(
        responses=[
            ModelResponse(
                content="",
                model="mock",
                metadata={},
                tool_calls=[ToolCall(id="c1", name="web_search", input={"query": "quick task"})],
            ),
            ModelResponse(content="done", model="mock", metadata={}),
        ]
    )

    agent = UniversalAgent(
        role=_build_test_role(),
        context=AgentContext(),
        llm=mock_llm,
        memory=manager,
        tools=[WebSearchTool()],
    )
    await agent.run("run one tool call")

    memories = await manager.recall_short_term(
        task_id=agent.context.task_id,
        limit=200,
    )

    # The tool result should be persisted
    assert any(m.metadata.get("tool") == "web_search" for m in memories)
