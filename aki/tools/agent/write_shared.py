"""
Tool: write_shared_state

Allows an agent to write to the task's SharedTaskMemory.
"""

import json
from typing import Any

from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.registry import ToolRegistry


@ToolRegistry.register
class WriteSharedStateTool(BaseTool):
    """Write a key-value pair to the task's shared memory."""

    name: str = "write_shared_state"
    description: str = (
        "Write a value to the shared task memory so other agents can access it. "
        "Value can be a string or a JSON-encoded object."
    )
    parameters: list[ToolParameter] = [
        ToolParameter(
            name="key",
            type="string",
            description="The key to write.",
            required=True,
        ),
        ToolParameter(
            name="value",
            type="string",
            description="The value to store (string or JSON-encoded object).",
            required=True,
        ),
    ]

    def __init__(self, shared_memory: Any = None, task_id: str = "") -> None:
        super().__init__()
        self.shared_memory = shared_memory
        self.task_id = task_id

    async def execute(self, **kwargs: Any) -> ToolResult:
        key = str(kwargs.get("key", "")).strip()
        raw_value = kwargs.get("value", "")

        if not key:
            return ToolResult.fail("'key' parameter is required.")

        if self.shared_memory is None:
            return ToolResult.fail("SharedTaskMemory not configured.")

        # Try to parse JSON, fall back to string
        value: Any = raw_value
        if isinstance(raw_value, str):
            try:
                value = json.loads(raw_value)
            except (json.JSONDecodeError, ValueError):
                value = raw_value

        await self.shared_memory.set(self.task_id, key, value)
        return ToolResult.ok(data={"key": key, "stored": True})
