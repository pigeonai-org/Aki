"""
Integration Tests for Aki

Tests the end-to-end flow of the agent system.
"""

import pytest

from aki.agent import (
    AgentContext,
    AgentOrchestrator,
    OrchestratorConfig,
    UniversalAgent,
)
from aki.agent.roles import Role
from aki.memory import MemoryItem, MemoryManager
from aki.models.base import ModelResponse, ToolCall
from aki.tools import BaseTool, ToolParameter, ToolRegistry, ToolResult


# ============================================================================
# Test Fixtures
# ============================================================================


class MockLLM:
    """Mock LLM for testing native tool calling."""

    def __init__(self, responses: list[ModelResponse] | None = None):
        self.responses = responses or []
        self.call_count = 0

    async def chat(self, messages, **kwargs):
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
        else:
            # Default: plain text response (signals completion)
            response = ModelResponse(content="done", model="mock", metadata={})
        self.call_count += 1
        return response


def _tool_call_response(tool_name: str, params: dict, call_id: str = "call_1") -> ModelResponse:
    """Helper to build a ModelResponse that requests a tool call."""
    return ModelResponse(
        content="",
        model="mock",
        metadata={},
        tool_calls=[ToolCall(id=call_id, name=tool_name, input=params)],
    )


def _text_response(text: str = "done") -> ModelResponse:
    """Helper to build a plain text ModelResponse (no tool calls = agent stops)."""
    return ModelResponse(content=text, model="mock", metadata={})


@ToolRegistry.register
class MockTool(BaseTool):
    """Mock tool for testing."""

    name = "mock_tool"
    description = "A mock tool for testing"
    parameters = [
        ToolParameter(name="input", type="string", description="Test input"),
    ]

    async def execute(self, input: str, **kwargs) -> ToolResult:
        return ToolResult.ok(data={"echo": input}, tool="mock_tool")


def _build_test_role() -> Role:
    return Role(
        name="test",
        persona="Test Agent Persona",
        system_prompt="Test System Prompt",
        allowed_tools=["mock_tool", "chunk_tool"],
    )


# ============================================================================
# Unit Tests
# ============================================================================


class TestToolSystem:
    """Tests for the tool system."""

    def test_tool_registration(self):
        """Test that tools are properly registered."""
        assert ToolRegistry.is_registered("mock_tool")
        tool = ToolRegistry.get("mock_tool")
        assert tool.name == "mock_tool"

    def test_tool_schema_generation(self):
        """Test OpenAI schema generation."""
        tool = ToolRegistry.get("mock_tool")
        schema = tool.to_openai_schema()

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "mock_tool"
        assert "input" in schema["function"]["parameters"]["properties"]

    def test_mcp_schema_generation(self):
        """Test MCP schema generation."""
        tool = ToolRegistry.get("mock_tool")
        schema = tool.to_mcp_schema()

        assert schema["name"] == "mock_tool"
        assert "inputSchema" in schema
        assert "input" in schema["inputSchema"]["properties"]

    @pytest.mark.asyncio
    async def test_tool_execution(self):
        """Test tool execution."""
        tool = ToolRegistry.get("mock_tool")
        result = await tool(input="test")

        assert result.success
        assert result.data["echo"] == "test"

    @pytest.mark.asyncio
    async def test_tool_validation(self):
        """Test tool parameter validation."""
        tool = ToolRegistry.get("mock_tool")

        # Missing required parameter
        result = await tool()
        assert not result.success
        assert "Missing required parameter" in result.error


class TestAgentSystem:
    """Tests for the agent system."""

    def test_agent_context_spawn_limits(self):
        """Test agent context spawn limits."""
        context = AgentContext(
            depth=2,
            max_depth=3,
            active_agents=4,
            max_agents=5,
        )

        assert context.can_spawn()

        context.depth = 3
        assert not context.can_spawn()

    @pytest.mark.asyncio
    async def test_agent_run(self):
        """Test basic agent run — model calls a tool then returns text."""
        mock_llm = MockLLM([
            _tool_call_response("mock_tool", {"input": "test"}),
            _text_response("all done"),
        ])

        context = AgentContext()
        agent = UniversalAgent(
            role=_build_test_role(),
            context=context,
            llm=mock_llm,
            tools=[MockTool()],
        )

        result = await agent.run("test task")
        assert result is not None
        assert mock_llm.call_count == 2


class TestMemorySystem:
    """Tests for the memory system."""

    @pytest.mark.asyncio
    async def test_memory_remember_recall(self):
        """Test basic memory operations."""
        manager = MemoryManager()

        # Add memory
        item = await manager.remember(
            content="Test memory",
            type="observation",
            task_id="test-task",
        )

        assert item.content == "Test memory"

        # Recall
        memories = await manager.recall(limit=5)
        assert len(memories) >= 1
        assert memories[0].content == "Test memory"

    @pytest.mark.asyncio
    async def test_memory_search(self):
        """Test memory search."""
        manager = MemoryManager()
        await manager.clear_short_term()

        await manager.remember(content="Hello world", type="observation")
        await manager.remember(content="Goodbye moon", type="observation")

        results = await manager.recall(query="world", limit=5)
        assert any("world" in m.content.lower() for m in results)


class TestOrchestrator:
    """Tests for the orchestrator."""

    def test_orchestrator_config(self):
        """Test orchestrator configuration."""
        config = OrchestratorConfig(
            max_agents_per_task=10,
            max_agent_depth=5,
        )

        assert config.max_agents_per_task == 10
        assert config.max_agent_depth == 5

    @pytest.mark.asyncio
    async def test_orchestrator_run(self):
        """Test orchestrator task execution."""
        mock_llm = MockLLM([_text_response("task completed")])

        orchestrator = AgentOrchestrator(
            config=OrchestratorConfig(default_agent_type="test"),
            llm=mock_llm,
        )

        result = await orchestrator.run_task("test task")
        assert result is not None


# ============================================================================
# Integration Tests
# ============================================================================


class TestEndToEndFlow:
    """End-to-end integration tests."""

    @pytest.mark.asyncio
    async def test_simple_task_flow(self):
        """Test a simple task: model calls tool then completes."""
        mock_llm = MockLLM([
            _tool_call_response("mock_tool", {"input": "hello"}),
            _text_response("processed"),
        ])

        context = AgentContext()
        agent = UniversalAgent(
            role=_build_test_role(),
            context=context,
            llm=mock_llm,
            tools=[MockTool()],
        )

        result = await agent.run("Process hello")

        assert result is not None
        assert mock_llm.call_count == 2  # one tool call + one completion

    @pytest.mark.asyncio
    async def test_memory_integration(self):
        """Test agent with memory integration."""
        mock_llm = MockLLM([_text_response("done")])

        memory = MemoryManager()
        await memory.remember(content="Previous task context", type="observation")

        context = AgentContext()
        agent = UniversalAgent(
            role=_build_test_role(),
            context=context,
            llm=mock_llm,
            memory=memory,
            tools=[MockTool()],
        )

        result = await agent.run("Continue from previous")
        assert result is not None

    @pytest.mark.asyncio
    async def test_tool_chunk_data_is_saved_to_memory(self):
        """Chunked audio metadata from tool results should persist in memory."""

        class ChunkTool(BaseTool):
            name = "chunk_tool"
            description = "Returns chunk metadata"
            parameters = [ToolParameter(name="audio_path", type="string", description="Audio path")]

            async def execute(self, audio_path: str, **kwargs) -> ToolResult:
                del kwargs
                return ToolResult.ok(
                    data={
                        "audio_path": audio_path,
                        "chunked_audio": [
                            {
                                "index": 1,
                                "audio_path": "chunk_0001.mp3",
                                "start_seconds": 0.0,
                                "end_seconds": 2.0,
                            }
                        ],
                    }
                )

        mock_llm = MockLLM([
            _tool_call_response("chunk_tool", {"audio_path": "demo.mp3"}),
            _text_response("done"),
        ])
        memory = MemoryManager()
        context = AgentContext()
        agent = UniversalAgent(
            role=_build_test_role(),
            context=context,
            llm=mock_llm,
            memory=memory,
            tools=[ChunkTool()],
        )

        await agent.run("Process chunked audio")
        memories = await memory.recall(task_id=context.task_id, limit=20)

        assert any(m.metadata.get("tool") == "chunk_tool" for m in memories)
        assert any(m.metadata.get("chunked_audio") for m in memories)


# ============================================================================
# Cleanup
# ============================================================================


@pytest.fixture(autouse=True)
def cleanup():
    """Cleanup after each test."""
    yield
