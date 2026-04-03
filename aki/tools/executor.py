"""
Tool Executor

Parallel execution engine for tool calls.
Partitions tool calls by concurrency safety and executes safe tools in parallel.
"""

import asyncio
import logging
import time
from typing import Any, AsyncGenerator, Optional

from pydantic import BaseModel, Field

from aki.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ToolProgress(BaseModel):
    """Progress event yielded during streaming tool execution."""

    tool_name: str = ""
    tool_call_id: str = ""
    event: str = "progress"  # "progress" | "complete" | "error"
    message: str = ""
    percentage: Optional[float] = None
    data: Any = None


class ToolCallRequest(BaseModel):
    """A single tool call to execute."""

    call_id: str = Field(..., description="Unique ID for this call")
    tool_name: str = Field(..., description="Name of the tool to invoke")
    params: dict[str, Any] = Field(default_factory=dict, description="Tool parameters")


class ToolCallResult(BaseModel):
    """Result of a single tool call execution."""

    call_id: str
    tool_name: str
    result: ToolResult
    duration_ms: float = 0.0


class ToolExecutor:
    """
    Executes tool calls with concurrency partitioning.

    Tools with ``concurrency_safe=True`` run in parallel via asyncio.gather().
    Unsafe tools run sequentially. Mixed batches are split: safe tools first
    (parallel), then unsafe tools (sequential).

    Usage::

        executor = ToolExecutor()
        results = await executor.execute_batch(calls, tools)
    """

    def __init__(
        self,
        result_store: Optional[Any] = None,
        hook_engine: Optional[Any] = None,
        max_parallel: int = 10,
    ) -> None:
        self._result_store = result_store
        self._hook_engine = hook_engine
        self._max_parallel = max_parallel

    def _find_tool(self, tool_name: str, tools: list[BaseTool]) -> Optional[BaseTool]:
        """Look up a tool by name."""
        for tool in tools:
            if tool.name == tool_name:
                return tool
        return None

    def _partition(
        self,
        calls: list[ToolCallRequest],
        tools: list[BaseTool],
    ) -> tuple[list[tuple[ToolCallRequest, BaseTool]], list[tuple[ToolCallRequest, BaseTool]]]:
        """
        Split calls into concurrent-safe and sequential groups.

        Returns:
            (safe_calls, unsafe_calls) each as list of (request, tool) pairs.
        """
        safe: list[tuple[ToolCallRequest, BaseTool]] = []
        unsafe: list[tuple[ToolCallRequest, BaseTool]] = []

        for call in calls:
            tool = self._find_tool(call.tool_name, tools)
            if tool is None:
                # Will produce an error result in execute
                unsafe.append((call, None))  # type: ignore[arg-type]
                continue

            if getattr(tool, "concurrency_safe", False):
                safe.append((call, tool))
            else:
                unsafe.append((call, tool))

        return safe, unsafe

    async def _execute_one(self, call: ToolCallRequest, tool: Optional[BaseTool]) -> ToolCallResult:
        """Execute a single tool call and wrap the result."""
        start = time.monotonic()

        if tool is None:
            result = ToolResult.fail(f"Unknown tool: {call.tool_name}")
        else:
            try:
                result = await tool(**call.params)
            except Exception as e:
                result = ToolResult.fail(f"Execution error: {e}")

        duration_ms = (time.monotonic() - start) * 1000

        # Store large results to disk if result_store is available
        if self._result_store is not None and result.success:
            try:
                result = await self._result_store.store_if_large(result, call.tool_name)
            except Exception:
                logger.debug("Failed to store large result for %s", call.tool_name)

        return ToolCallResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            result=result,
            duration_ms=duration_ms,
        )

    async def execute_batch(
        self,
        calls: list[ToolCallRequest],
        tools: list[BaseTool],
    ) -> list[ToolCallResult]:
        """
        Execute a batch of tool calls with concurrency optimization.

        Safe tools run in parallel, unsafe tools run sequentially.
        Results are returned in the same order as the input calls.
        """
        if not calls:
            return []

        safe_calls, unsafe_calls = self._partition(calls, tools)
        results_map: dict[str, ToolCallResult] = {}

        # Execute safe tools in parallel (capped)
        if safe_calls:
            semaphore = asyncio.Semaphore(self._max_parallel)

            async def _limited(call: ToolCallRequest, tool: BaseTool) -> ToolCallResult:
                async with semaphore:
                    return await self._execute_one(call, tool)

            safe_results = await asyncio.gather(
                *[_limited(call, tool) for call, tool in safe_calls]
            )
            for r in safe_results:
                results_map[r.call_id] = r

            logger.debug("Executed %d safe tools in parallel", len(safe_calls))

        # Execute unsafe tools sequentially
        for call, tool in unsafe_calls:
            r = await self._execute_one(call, tool)
            results_map[r.call_id] = r

        if unsafe_calls:
            logger.debug("Executed %d unsafe tools sequentially", len(unsafe_calls))

        # Return in original order
        return [results_map[call.call_id] for call in calls if call.call_id in results_map]

    async def execute_batch_streaming(
        self,
        calls: list[ToolCallRequest],
        tools: list[BaseTool],
    ) -> AsyncGenerator[ToolProgress, None]:
        """
        Execute tools and yield progress events.

        Each tool completion yields a ToolProgress with event="complete".
        """
        if not calls:
            return

        safe_calls, unsafe_calls = self._partition(calls, tools)

        # Safe tools: execute in parallel, yield completions as they arrive
        if safe_calls:
            tasks = {
                asyncio.create_task(self._execute_one(call, tool)): call
                for call, tool in safe_calls
            }
            for coro in asyncio.as_completed(tasks):
                result = await coro
                yield ToolProgress(
                    tool_name=result.tool_name,
                    tool_call_id=result.call_id,
                    event="complete" if result.result.success else "error",
                    message=result.result.error or "",
                    data=result,
                )

        # Unsafe tools: yield one by one
        for call, tool in unsafe_calls:
            result = await self._execute_one(call, tool)
            yield ToolProgress(
                tool_name=result.tool_name,
                tool_call_id=result.call_id,
                event="complete" if result.result.success else "error",
                message=result.result.error or "",
                data=result,
            )
