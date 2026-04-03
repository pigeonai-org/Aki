"""
Agent Orchestrator

Manages multi-agent collaboration, including:
- Task dispatch to the main agent
- Depth and count limit enforcement
- Agent lifecycle management
"""

import copy
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from aki.agent.agent_registry import AgentRegistry
from aki.agent.base import UniversalAgent
from aki.agent.communication.bus import AgentBus
from aki.agent.identity import discover_agent_definitions
from aki.agent.state import AgentContext
from aki.agent.task_registry import TaskRegistry
from aki.context.manager import ContextManager
from aki.hooks.engine import HookEngine
from aki.hooks.permission import PermissionEngine
from aki.memory.shared import SharedTaskMemory
from aki.models.types.llm import LLMInterface
from aki.resilience.recovery import ErrorRecoveryHandler
from aki.tools.base import BaseTool
from aki.tools.registry import ToolRegistry


class OrchestratorConfig(BaseModel):
    """Orchestrator configuration."""

    max_agents_per_task: int = Field(
        default=5,
        description="Maximum number of agents allowed per task",
    )
    max_agent_depth: int = Field(
        default=3,
        description="Maximum agent call chain depth",
    )
    default_agent_type: str = Field(
        default="main",
        description="Default agent type for task execution",
    )


class AgentOrchestrator:
    """
    Agent Orchestrator.

    Entry point for running tasks with the multi-agent system.
    Manages agent lifecycle and enforces resource limits.
    """

    def __init__(
        self,
        config: Optional[OrchestratorConfig] = None,
        llm: Optional[LLMInterface] = None,
        memory: Optional[Any] = None,
        tools: Optional[list[BaseTool]] = None,
        auto_load_tools: bool = True,
    ):
        """
        Initialize the orchestrator.

        Args:
            config: Orchestrator configuration
            llm: LLM interface for agents
            memory: Memory manager for agents
            tools: List of tools to provide to agents
            auto_load_tools: Automatically load all registered tools
        """
        self.config = config or OrchestratorConfig()
        self.llm = llm
        self.memory = memory

        # Phase 2: context management + error recovery
        self._context_manager = ContextManager()
        self._error_handler = ErrorRecoveryHandler(context_manager=self._context_manager)

        # Phase 3: agent registry for persistent identity lookup
        self._agent_registry = AgentRegistry()
        self._load_agent_definitions()

        # Phase 4: hook + permission system
        self._hook_engine = HookEngine()
        self._permission_engine = PermissionEngine(self._hook_engine)

        # Phase 5: agent communication
        self._shared_memory = SharedTaskMemory()

        # Phase 6: task registry for parallel agents
        self._task_registry = TaskRegistry()

        # Initialize tools
        if tools is not None:
            self.tools = tools
        elif auto_load_tools:
            # Auto-load all registered tools
            self.tools = self._load_registered_tools()
        else:
            self.tools = []

        # Track active agents per task
        self._active_tasks: dict[str, dict[str, UniversalAgent]] = {}

    def _load_agent_definitions(self) -> None:
        """Load agent definitions from .aki/agents/ if available."""
        try:
            from aki.config.settings import get_settings
            agents_dir = get_settings().agent.agents_dir
        except Exception:
            agents_dir = ".aki/agents"

        definitions = discover_agent_definitions(agents_dir)
        for defn in definitions.values():
            self._agent_registry.register(defn)

    def _load_registered_tools(self) -> list[BaseTool]:
        """Load all registered tools from the ToolRegistry."""
        tools = []
        for tool_name in ToolRegistry.list_tools():
            try:
                tool = ToolRegistry.get(tool_name)
                tools.append(tool)
            except Exception:
                pass  # Skip tools that fail to instantiate
        return tools

    async def run_task(
        self,
        task: str,
        agent_type: Optional[str] = None,
    ) -> Any:
        """
        Execute a task with the multi-agent system.

        This is the main entry point for task execution.

        Args:
            task: Task description
            agent_type: Agent type to use (defaults to config.default_agent_type)

        Returns:
            Result from the agent execution
        """
        if self.llm is None:
            raise ValueError("LLM not configured. Set llm in orchestrator.")

        agent_type = agent_type or self.config.default_agent_type
        task_id = str(uuid4())

        # Initialize task tracking
        self._active_tasks[task_id] = {}

        # Create an isolated workspace directory for this task
        import time
        from pathlib import Path

        workspace_path = Path("outputs") / f"task_{int(time.time())}_{task_id[:8]}"
        workspace_path.mkdir(parents=True, exist_ok=True)

        try:
            # Create root context
            context = AgentContext(
                task_id=task_id,
                depth=0,
                max_depth=self.config.max_agent_depth,
                max_agents=self.config.max_agents_per_task,
                active_agents=1,
                workspace_dir=str(workspace_path.resolve()),
            )

            # Phase 5: create per-task bus
            task_bus = AgentBus()

            # Inject dependencies into per-task tool copies (avoid mutating shared state)
            task_tools = [copy.copy(t) for t in self.tools]
            for t in task_tools:
                if t.name == "delegate_to_worker":
                    t.context = context
                    t.llm = self.llm
                    t.all_tools = task_tools
                    t.agent_registry = self._agent_registry
                    t.shared_memory = self._shared_memory
                    t.task_bus = task_bus
                    t.task_registry = self._task_registry
                elif t.name == "check_agent_task":
                    t.task_registry = self._task_registry
                elif hasattr(t, "all_tools") and t.name.endswith("_pipeline"):
                    t.all_tools = task_tools

            # Create and run Orchestrator agent
            agent = UniversalAgent(
                context=context,
                llm=self.llm,
                memory=self.memory,
                tools=task_tools,
                context_manager=self._context_manager,
                error_handler=self._error_handler,
                hook_engine=self._hook_engine,
                permission_engine=self._permission_engine,
                agent_name="orchestrator",
            )
            # Register orchestrator on the bus
            task_bus.register_agent(agent.agent_id, f"task_{task_id[:8]}:Orchestrator")

            # Track the agent
            self._active_tasks[task_id][agent.agent_id] = agent

            # Run the agent
            result = await agent.run(task)

            return result

        finally:
            # Cleanup
            if task_id in self._active_tasks:
                del self._active_tasks[task_id]
            # Phase 5: cleanup shared memory for this task
            await self._shared_memory.clear_task(task_id)

    def create_session_agent(
        self,
        user_id: str = "",
    ) -> tuple[UniversalAgent, AgentContext]:
        """Create a persistent agent + context for multi-turn sessions.

        Unlike ``run_task()`` which creates a throwaway agent per task, this
        returns an agent that should be kept alive across conversation turns
        and driven via ``agent.run_turn()``.

        Returns:
            (agent, context) tuple — caller is responsible for keeping these
            alive for the duration of the session.
        """
        if self.llm is None:
            raise ValueError("LLM not configured. Set llm in orchestrator.")

        import time
        from pathlib import Path

        task_id = str(uuid4())
        workspace_path = Path("outputs") / f"session_{int(time.time())}_{task_id[:8]}"
        workspace_path.mkdir(parents=True, exist_ok=True)

        context = AgentContext(
            task_id=task_id,
            depth=0,
            max_depth=self.config.max_agent_depth,
            max_agents=self.config.max_agents_per_task,
            active_agents=1,
            workspace_dir=str(workspace_path.resolve()),
        )

        # Inject dependencies into per-session tool copies (avoid mutating shared state)
        task_bus = AgentBus()
        session_tools = [copy.copy(t) for t in self.tools]
        for t in session_tools:
            if t.name == "delegate_to_worker":
                t.context = context
                t.llm = self.llm
                t.all_tools = session_tools
                t.agent_registry = self._agent_registry
                t.shared_memory = self._shared_memory
                t.task_bus = task_bus
            elif t.name == "check_agent_task":
                t.task_registry = self._task_registry
            elif hasattr(t, "all_tools") and t.name.endswith("_pipeline"):
                t.all_tools = session_tools

        # Initialize AkiMemorySystem for the session
        memory_system = None
        try:
            from aki.memory.manager import AkiMemorySystem
            memory_system = AkiMemorySystem(user_id=user_id)
            memory_system.start_session()
        except Exception:
            pass

        agent = UniversalAgent(
            context=context,
            llm=self.llm,
            memory=self.memory,
            tools=session_tools,
            context_manager=self._context_manager,
            error_handler=self._error_handler,
            hook_engine=self._hook_engine,
            permission_engine=self._permission_engine,
            memory_system=memory_system,
            agent_name="session",
        )

        return agent, context

    def get_active_agent_count(self, task_id: str) -> int:
        """Get the number of active agents for a task."""
        return len(self._active_tasks.get(task_id, {}))

    def get_active_task_count(self) -> int:
        """Get the number of active tasks."""
        return len(self._active_tasks)

    async def cancel_task(self, task_id: str) -> None:
        """
        Cancel a running task.

        Args:
            task_id: Task ID to cancel
        """
        if task_id in self._active_tasks:
            del self._active_tasks[task_id]

    def set_llm(self, llm: LLMInterface) -> None:
        """Set the LLM interface."""
        self.llm = llm

    def set_memory(self, memory: Any) -> None:
        """Set the memory manager."""
        self.memory = memory


# Global orchestrator instance
_orchestrator: Optional[AgentOrchestrator] = None


def get_orchestrator() -> AgentOrchestrator:
    """Get the global orchestrator instance (singleton)."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator


def reset_orchestrator() -> None:
    """Reset the global orchestrator instance (useful for testing)."""
    global _orchestrator
    _orchestrator = None
