"""
Tool: read_shared_state

Allows an agent to read from the task's SharedTaskMemory.
"""

from typing import Any

from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.registry import ToolRegistry


@ToolRegistry.register
class ReadSharedStateTool(BaseTool):
    """Read a key from the task's shared memory."""

    name: str = "read_shared_state"
    description: str = (
        "Read a value from the shared task memory. "
        "Use key='*' to list all available keys."
    )
    parameters: list[ToolParameter] = [
        ToolParameter(
            name="key",
            type="string",
            description="The key to read, or '*' to list all keys.",
            required=True,
        ),
    ]
    concurrency_safe: bool = True

    def __init__(self, shared_memory: Any = None, task_id: str = "") -> None:
        super().__init__()
        self.shared_memory = shared_memory
        self.task_id = task_id

    async def execute(self, **kwargs: Any) -> ToolResult:
        key = str(kwargs.get("key", "")).strip()

        if not key:
            return ToolResult.fail("'key' parameter is required.")

        if self.shared_memory is None:
            return ToolResult.fail("SharedTaskMemory not configured.")

        if key == "*":
            keys = await self.shared_memory.keys(self.task_id)
            return ToolResult.ok(data={"keys": keys})

        value = await self.shared_memory.get(self.task_id, key)
        if value is None:
            return ToolResult.fail(f"Key '{key}' not found in shared state.")

        return ToolResult.ok(data={"key": key, "value": value})
