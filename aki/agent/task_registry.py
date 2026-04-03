"""
Task Registry

Central registry for tracking agent tasks (foreground and background).
Supports task lifecycle (create → running → completed/failed/cancelled)
and agent instance lookup by ID or role name.
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AgentTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentTask(BaseModel):
    """A tracked agent task (foreground or background)."""

    task_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: str = ""
    role_name: str = ""
    description: str = ""
    status: AgentTaskStatus = AgentTaskStatus.RUNNING
    result: Any = None
    error: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    completed_at: Optional[float] = None

    model_config = {"arbitrary_types_allowed": True}


class TaskRegistry:
    """Central registry for agent tasks.

    Tracks both foreground and background agent tasks, provides lookup
    by task_id or role_name, and supports cancellation.

    Usage::

        registry = TaskRegistry()
        task = registry.create("agent-123", "Researcher", "Search for papers")
        # ... later
        registry.complete(task.task_id, result="Found 5 papers")
    """

    def __init__(self) -> None:
        self._tasks: dict[str, AgentTask] = {}
        self._agents: dict[str, Any] = {}  # agent_id → agent instance
        self._asyncio_tasks: dict[str, asyncio.Task[Any]] = {}  # task_id → asyncio.Task
        self._role_to_agent: dict[str, str] = {}  # role_name → agent_id

    def create(
        self,
        agent_id: str,
        role_name: str = "",
        description: str = "",
    ) -> AgentTask:
        """Create and register a new agent task."""
        task = AgentTask(
            agent_id=agent_id,
            role_name=role_name,
            description=description,
        )
        self._tasks[task.task_id] = task
        if role_name:
            self._role_to_agent[role_name] = agent_id
        logger.debug("Task created: %s (agent=%s, role=%s)", task.task_id[:8], agent_id[:8], role_name)
        return task

    def register_agent(self, agent_id: str, agent: Any, role_name: str = "") -> None:
        """Register an agent instance for lookup."""
        self._agents[agent_id] = agent
        if role_name:
            self._role_to_agent[role_name] = agent_id

    def set_asyncio_task(self, task_id: str, asyncio_task: asyncio.Task[Any]) -> None:
        """Associate an asyncio.Task with a registry task."""
        self._asyncio_tasks[task_id] = asyncio_task

    def get(self, task_id: str) -> Optional[AgentTask]:
        """Get a task by ID."""
        return self._tasks.get(task_id)

    def get_agent(self, agent_id_or_name: str) -> Any | None:
        """Get an agent instance by agent_id or role_name."""
        if agent_id_or_name in self._agents:
            return self._agents[agent_id_or_name]
        # Try role name lookup
        agent_id = self._role_to_agent.get(agent_id_or_name)
        if agent_id:
            return self._agents.get(agent_id)
        return None

    def resolve_name(self, name: str) -> str | None:
        """Resolve a role name to an agent_id."""
        if name in self._agents:
            return name
        return self._role_to_agent.get(name)

    def complete(self, task_id: str, result: Any = None) -> None:
        """Mark a task as completed."""
        task = self._tasks.get(task_id)
        if task:
            task.status = AgentTaskStatus.COMPLETED
            task.result = result
            task.completed_at = time.time()

    def fail(self, task_id: str, error: str) -> None:
        """Mark a task as failed."""
        task = self._tasks.get(task_id)
        if task:
            task.status = AgentTaskStatus.FAILED
            task.error = error
            task.completed_at = time.time()

    def cancel(self, task_id_or_name: str) -> bool:
        """Cancel a task by ID or role name. Returns True if found and cancelled."""
        # Resolve name to task_id
        task_id = task_id_or_name
        if task_id not in self._tasks:
            agent_id = self._role_to_agent.get(task_id_or_name)
            if agent_id:
                for tid, t in self._tasks.items():
                    if t.agent_id == agent_id and t.status == AgentTaskStatus.RUNNING:
                        task_id = tid
                        break

        task = self._tasks.get(task_id)
        if task is None or task.status != AgentTaskStatus.RUNNING:
            return False

        task.status = AgentTaskStatus.CANCELLED
        task.completed_at = time.time()

        # Cancel the asyncio task if present
        asyncio_task = self._asyncio_tasks.get(task_id)
        if asyncio_task and not asyncio_task.done():
            asyncio_task.cancel()

        return True

    def cancel_all(self) -> int:
        """Cancel all running tasks. Returns count cancelled."""
        count = 0
        for task_id in list(self._tasks):
            if self.cancel(task_id):
                count += 1
        return count

    def list_active(self) -> list[AgentTask]:
        """List all running tasks."""
        return [t for t in self._tasks.values() if t.status == AgentTaskStatus.RUNNING]

    def list_all(self) -> list[AgentTask]:
        """List all tasks."""
        return list(self._tasks.values())

    def cleanup(self, max_age_seconds: float = 3600) -> int:
        """Remove completed/failed/cancelled tasks older than max_age_seconds."""
        now = time.time()
        to_remove = [
            tid for tid, task in self._tasks.items()
            if task.status in (AgentTaskStatus.COMPLETED, AgentTaskStatus.FAILED, AgentTaskStatus.CANCELLED)
            and now - task.created_at > max_age_seconds
        ]
        for tid in to_remove:
            task = self._tasks.pop(tid)
            self._agents.pop(task.agent_id, None)
            self._asyncio_tasks.pop(tid, None)
            if task.role_name and task.role_name in self._role_to_agent:
                self._role_to_agent.pop(task.role_name, None)
        return len(to_remove)

    async def wait(self, task_id: str, timeout: float = 300.0) -> AgentTask | None:
        """Wait for a task to complete. Returns the task or None on timeout."""
        asyncio_task = self._asyncio_tasks.get(task_id)
        if asyncio_task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(asyncio_task), timeout=timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
        return self._tasks.get(task_id)
