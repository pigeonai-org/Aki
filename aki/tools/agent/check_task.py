"""
Tool: check_agent_task

Query status or wait for a background agent task to complete.
"""

from typing import Any

from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.registry import ToolRegistry


@ToolRegistry.register
class CheckAgentTaskTool(BaseTool):
    """Check the status of a background agent task, or wait for it to finish."""

    name: str = "check_agent_task"
    description: str = (
        "Check status of a background agent task by task_id. "
        "Set wait=true to block until the task completes."
    )
    parameters: list[ToolParameter] = [
        ToolParameter(
            name="task_id",
            type="string",
            description="The task_id returned by delegate_to_worker(run_in_background=true).",
            required=True,
        ),
        ToolParameter(
            name="wait",
            type="boolean",
            description="If true, wait for the task to complete before returning.",
            required=False,
        ),
        ToolParameter(
            name="timeout",
            type="integer",
            description="Max seconds to wait (default 300). Only used when wait=true.",
            required=False,
        ),
    ]
    concurrency_safe: bool = True

    def __init__(self, task_registry: Any = None) -> None:
        super().__init__()
        self.task_registry = task_registry

    async def execute(self, **kwargs: Any) -> ToolResult:
        task_id = str(kwargs.get("task_id", "")).strip()
        wait = bool(kwargs.get("wait", False))
        timeout = int(kwargs.get("timeout", 300))

        if not task_id:
            return ToolResult.fail("task_id is required.")

        if self.task_registry is None:
            return ToolResult.fail("TaskRegistry not configured.")

        if wait:
            task = await self.task_registry.wait(task_id, timeout=timeout)
        else:
            task = self.task_registry.get(task_id)

        if task is None:
            return ToolResult.fail(f"Task '{task_id}' not found.")

        return ToolResult.ok(data={
            "task_id": task.task_id,
            "status": task.status.value,
            "role_name": task.role_name,
            "result": task.result,
            "error": task.error,
        })
