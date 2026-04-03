"""Tests for skill-aware orchestration fallback and dynamic worker creation."""

from __future__ import annotations

from typing import Any

import pytest

from aki.agent.roles import get_role
from aki.agent.state import AgentContext
from aki.tools import ToolRegistry
from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.delegate_to_worker import DelegateToWorkerTool


class _ScriptedLLM:
    """Deterministic chat stub that returns scripted ModelResponse objects in order.

    Accepts a list of ModelResponse objects. As a convenience, plain strings are
    interpreted as text responses (no tool calls).
    """

    def __init__(self, responses: list[Any]):
        from aki.models.base import ModelResponse
        self._responses: list[Any] = [
            r if not isinstance(r, str) else ModelResponse(content=r, model="mock-llm", metadata={})
            for r in responses
        ]
        self._calls = 0

    async def chat(self, messages, **kwargs):  # noqa: ANN001
        del messages, kwargs
        if self._calls < len(self._responses):
            resp = self._responses[self._calls]
        else:
            resp = self._responses[-1]
        self._calls += 1
        return resp


class _EchoTool(BaseTool):
    """Simple text echo tool used by dynamic worker tests."""

    name = "echo_tool"
    description = "Echo tool for tests"
    parameters = [ToolParameter(name="text", type="string", description="text")]

    async def execute(self, text: str, **kwargs: Any) -> ToolResult:
        del kwargs
        return ToolResult.ok(data={"text": text})


class _FakeReadSkillTool(BaseTool):
    """Fake read_skill to verify dynamic-role disallowed-tool checks."""

    name = "read_skill"
    description = "Fake read_skill for validation tests"
    parameters = [ToolParameter(name="skill_name", type="string", description="skill")]

    async def execute(self, skill_name: str, **kwargs: Any) -> ToolResult:
        del skill_name, kwargs
        return ToolResult.ok(data={"ok": True})


@pytest.mark.asyncio
async def test_skills_search_returns_available_skills():
    """skills_search should list currently available skill metadata."""
    tool = ToolRegistry.get("skills_search")
    result = await tool()

    assert result.success
    names = {str(item.get("name")) for item in (result.data or {}).get("skills", [])}
    assert "agent-creation" in names
    assert "subtitle-translation" in names


@pytest.mark.asyncio
async def test_skills_search_query_returns_best_match():
    """skills_search should rank subtitle workflow query to subtitle-translation."""
    tool = ToolRegistry.get("skills_search")
    result = await tool(query="subtitle translation workflow", limit=3)

    assert result.success
    assert (result.data or {}).get("matches")
    assert (result.data or {}).get("best_match") == "subtitle-translation"


@pytest.mark.asyncio
async def test_read_skill_missing_returns_suggestions_and_metadata():
    """read_skill should soft-fail with available skills and suggestions."""
    tool = ToolRegistry.get("read_skill")
    result = await tool(skill_name="subtitle-translatoin")

    assert not result.success
    assert "skills_search" in str(result.error)
    assert (result.metadata or {}).get("requested_skill") == "subtitle-translatoin"
    assert isinstance((result.metadata or {}).get("available_skills"), list)
    assert isinstance((result.metadata or {}).get("suggestions"), list)
    assert (result.metadata or {}).get("hint") == "Use skills_search first"


@pytest.mark.asyncio
async def test_delegate_dynamic_role_success():
    """Unknown worker role should run when dynamic-role fields are supplied."""
    from aki.models.base import ModelResponse, ToolCall

    delegate_tool = DelegateToWorkerTool(
        context=AgentContext(),
        llm=_ScriptedLLM(
            [
                ModelResponse(
                    content="",
                    model="mock",
                    metadata={},
                    tool_calls=[ToolCall(id="c1", name="echo_tool", input={"text": "hello"})],
                ),
                ModelResponse(content="done", model="mock", metadata={}),
            ]
        ),
        all_tools=[_EchoTool()],
    )

    result = await delegate_tool(
        worker_role="AdHocTextWorker",
        task_instruction="Use tools to complete this request.",
        worker_persona="You are a dynamic helper role.",
        worker_system_prompt="Use the assigned tools and then complete.",
        worker_allowed_tools=["echo_tool"],
    )

    assert result.success
    assert (result.data or {}).get("worker_output") == "done"


@pytest.mark.asyncio
async def test_delegate_unknown_role_requires_dynamic_fields():
    """Unknown worker role without dynamic config should fail with guidance."""
    delegate_tool = DelegateToWorkerTool(
        context=AgentContext(),
        llm=_ScriptedLLM(['{"type":"complete","params":{"result":"done"}}']),
        all_tools=[_EchoTool()],
    )

    result = await delegate_tool(
        worker_role="UnknownRole",
        task_instruction="Do something",
    )

    assert not result.success
    assert "worker_persona" in str(result.error)
    assert "worker_system_prompt" in str(result.error)
    assert "worker_allowed_tools" in str(result.error)


@pytest.mark.asyncio
async def test_delegate_dynamic_role_rejects_unknown_tools():
    """Dynamic worker should fail if it references unregistered tool names."""
    delegate_tool = DelegateToWorkerTool(
        context=AgentContext(),
        llm=_ScriptedLLM(['{"type":"complete","params":{"result":"done"}}']),
        all_tools=[_EchoTool()],
    )

    result = await delegate_tool(
        worker_role="UnknownRole",
        task_instruction="Do something",
        worker_persona="dynamic persona",
        worker_system_prompt="dynamic system prompt",
        worker_allowed_tools=["nonexistent_tool"],
    )

    assert not result.success
    assert "unknown tools" in str(result.error)
    assert "nonexistent_tool" in str(result.error)


@pytest.mark.asyncio
async def test_delegate_dynamic_role_rejects_orchestrator_tools():
    """Dynamic worker should block orchestration-only tool exposure."""
    delegate_tool = DelegateToWorkerTool(
        context=AgentContext(),
        llm=_ScriptedLLM(['{"type":"complete","params":{"result":"done"}}']),
        all_tools=[_EchoTool(), _FakeReadSkillTool()],
    )

    result = await delegate_tool(
        worker_role="UnknownRole",
        task_instruction="Do something",
        worker_persona="dynamic persona",
        worker_system_prompt="dynamic system prompt",
        worker_allowed_tools=["echo_tool", "read_skill"],
    )

    assert not result.success
    assert "disallowed tools" in str(result.error)
    assert "read_skill" in str(result.error)


@pytest.mark.asyncio
async def test_generalist_role_is_available_and_delegatable():
    """Generalist should be loaded from role frontmatter and runnable via delegation."""
    generalist = get_role("Generalist")
    assert generalist.name == "Generalist"
    assert "file_read" in generalist.allowed_tools
    assert "web_search" in generalist.allowed_tools

    delegate_tool = DelegateToWorkerTool(
        context=AgentContext(),
        llm=_ScriptedLLM(["ok"]),  # plain text → agent returns immediately
        all_tools=[],
    )
    result = await delegate_tool(
        worker_role="Generalist",
        task_instruction="Summarize context and return done.",
        context_data={"note": "hello"},
    )

    assert result.success
    assert (result.data or {}).get("worker_output") == "ok"


@pytest.mark.asyncio
async def test_delegate_respects_spawn_limits():
    """Delegation should stop when context cannot spawn additional workers."""
    blocked_context = AgentContext(depth=3, max_depth=3, active_agents=1, max_agents=5)
    delegate_tool = DelegateToWorkerTool(
        context=blocked_context,
        llm=_ScriptedLLM(['{"type":"complete","params":{"result":"done"}}']),
        all_tools=[],
    )

    result = await delegate_tool(
        worker_role="Generalist",
        task_instruction="Do a tiny task.",
    )

    assert not result.success
    assert "Cannot spawn worker agent" in str(result.error)
