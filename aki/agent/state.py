"""
Agent Context

Tracks the call chain depth and resource limits for spawned agents.
AgentState has been removed — the native tool calling loop manages iteration internally.
"""

from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class AgentContext(BaseModel):
    """
    Agent execution context.

    Passed to child agents to track depth and enforce resource limits.
    """

    task_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for the task",
    )
    depth: int = Field(
        default=0,
        description="Current depth in the agent call chain (0 = root agent)",
    )
    parent_agent_id: Optional[str] = Field(
        default=None,
        description="ID of the parent agent (None for root)",
    )
    max_depth: int = Field(
        default=3,
        description="Maximum allowed depth (prevents infinite recursion)",
    )
    active_agents: int = Field(
        default=0,
        description="Number of currently active agents in this task",
    )
    max_agents: int = Field(
        default=5,
        description="Maximum number of agents allowed per task",
    )
    workspace_dir: Optional[str] = Field(
        default=None,
        description="Absolute path to the workspace directory for outputting intermediate files",
    )

    # Phase 3: agent identity + shared memory references
    agent_identity: Optional[Any] = Field(
        default=None,
        description="AgentIdentity for persistent agent instances (Phase 3)",
    )
    shared_memory: Optional[Any] = Field(
        default=None,
        description="SharedTaskMemory instance for inter-agent communication (Phase 3)",
    )

    def can_spawn(self) -> bool:
        """Check if spawning a new agent is allowed."""
        return self.depth < self.max_depth and self.active_agents < self.max_agents

    def create_child_context(self, parent_id: str) -> "AgentContext":
        """Create a context for a child agent."""
        return AgentContext(
            task_id=self.task_id,
            depth=self.depth + 1,
            parent_agent_id=parent_id,
            max_depth=self.max_depth,
            active_agents=self.active_agents + 1,
            max_agents=self.max_agents,
            workspace_dir=self.workspace_dir,
        )
