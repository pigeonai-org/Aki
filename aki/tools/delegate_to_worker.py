"""
Tool for Orchestrator to delegate tasks to specialized worker agents.

This is purely for spawning subagent instances with LLM reasoning loops.
Deterministic pipelines (MediaExtractor, Localizer, QAEditor) have been
extracted to aki/tools/pipeline/ and can be called directly by any agent.
"""

from typing import Any

from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.registry import ToolRegistry


@ToolRegistry.register
class DelegateToWorkerTool(BaseTool):
    """Spawn a UniversalAgent subagent for a specialized task.

    Use this when you need an LLM reasoning loop for a task.
    For deterministic pipelines, use the pipeline tools instead:
    - media_extract_pipeline (audio extract → VAD → transcribe)
    - localize_pipeline (translate → edit subtitles)
    - qa_edit_pipeline (proofread → write SRT)
    """

    name: str = "delegate_to_worker"
    description: str = (
        "Spawn a worker agent with an LLM reasoning loop. "
        "For deterministic pipelines use media_extract_pipeline / "
        "localize_pipeline / qa_edit_pipeline instead."
    )
    parameters: list[ToolParameter] = [
        ToolParameter(
            name="worker_role",
            type="string",
            description=(
                "Worker name for identification (e.g. 'Generalist'). "
                "Used as agent_name for logging."
            ),
            required=True,
        ),
        ToolParameter(
            name="task_instruction",
            type="string",
            description="Natural language instructions for the worker.",
            required=True,
        ),
        ToolParameter(
            name="context_data",
            type="object",
            description="Key-value context dict passed to the worker.",
            required=False,
        ),
        ToolParameter(
            name="worker_persona",
            type="string",
            description="Dynamic role persona (required for non-predefined roles).",
            required=False,
        ),
        ToolParameter(
            name="worker_system_prompt",
            type="string",
            description="Dynamic role system prompt (required for non-predefined roles).",
            required=False,
        ),
        ToolParameter(
            name="worker_allowed_tools",
            type="array",
            description="Dynamic role tool whitelist (required for non-predefined roles).",
            required=False,
        ),
        ToolParameter(
            name="run_in_background",
            type="boolean",
            description=(
                "If true, spawn the worker as a background task and return immediately "
                "with a task_id. Use check_agent_task to poll or wait for the result."
            ),
            required=False,
        ),
    ]

    def __init__(
        self,
        context: Any = None,
        llm: Any = None,
        all_tools: list[BaseTool] | None = None,
        agent_registry: Any = None,
    ) -> None:
        super().__init__()
        self.context = context
        self.llm = llm
        self.all_tools: list[BaseTool] = all_tools or []
        self.agent_registry = agent_registry
        self.shared_memory: Any = None
        self.task_bus: Any = None
        self.task_registry: Any = None  # TaskRegistry for background execution
        self._callback: Any = None  # AgentCallback for spawned workers

    async def execute(self, **kwargs: Any) -> ToolResult:
        worker_role_name = str(kwargs.get("worker_role") or "").strip()
        task_instruction = str(kwargs.get("task_instruction") or "")
        raw_context = kwargs.get("context_data", {})
        context_data = raw_context if isinstance(raw_context, dict) else {}

        if not worker_role_name:
            return ToolResult.fail("worker_role is required.")

        if not self.context or not self.llm:
            return ToolResult.fail(
                "delegate_to_worker must be initialized with context and llm."
            )

        # --- Spawn check ---
        if not self.context.can_spawn():
            return ToolResult.fail(
                f"Cannot spawn: depth={self.context.depth}/{self.context.max_depth}, "
                f"agents={self.context.active_agents}/{self.context.max_agents}"
            )

        # --- Build task ---
        context_str = "\n".join(f"{k}: {v}" for k, v in context_data.items())
        full_task = f"{task_instruction}\n\nContext:\n{context_str}" if context_str else task_instruction

        # --- Spawn and run ---
        run_in_background = bool(kwargs.get("run_in_background", False))
        child_context = self.context.create_child_context("orchestrator-delegation")

        from aki.agent.base import UniversalAgent

        worker = UniversalAgent(
            context=child_context,
            llm=self.llm,
            tools=self.all_tools,
            callback=self._callback,
            agent_name=worker_role_name,
        )

        # Register worker on bus if available
        if self.task_bus:
            self.task_bus.register_agent(
                worker.agent_id, f"task:{worker_role_name}"
            )

        # Emit AGENT_SPAWN event for UI visibility
        if self._callback is not None:
            import asyncio as _aio
            try:
                _aio.get_event_loop().create_task(
                    self._callback.on_tool_start(
                        worker.agent_id, "__agent_spawn__",
                        {"role_name": worker_role_name, "background": run_in_background},
                    )
                )
            except Exception:
                pass

        # Register worker in task_registry (both foreground and background)
        if self.task_registry is not None:
            self.task_registry.register_agent(worker.agent_id, worker, worker_role_name)

        if run_in_background and self.task_registry is not None:
            # --- Background execution: return immediately with task_id ---
            import asyncio

            task = self.task_registry.create(
                worker.agent_id, role_name=worker_role_name, description=task_instruction[:200],
            )

            async def _run_bg() -> None:
                try:
                    result = await worker.run(full_task)
                    self.task_registry.complete(task.task_id, result=result)
                except asyncio.CancelledError:
                    self.task_registry.cancel(task.task_id)
                except Exception as e:
                    self.task_registry.fail(task.task_id, error=str(e))

            asyncio_task = asyncio.create_task(_run_bg())
            self.task_registry.set_asyncio_task(task.task_id, asyncio_task)

            return ToolResult.ok(data={
                "task_id": task.task_id,
                "agent_id": worker.agent_id,
                "role_name": worker_role_name,
                "status": "running",
                "message": f"Background worker '{worker_role_name}' started. Use check_agent_task to poll.",
            })

        # --- Foreground execution: block until done ---
        if self.task_registry is not None:
            fg_task = self.task_registry.create(
                worker.agent_id, role_name=worker_role_name, description=task_instruction[:200],
            )
        try:
            result = await worker.run(full_task)
            if self.task_registry is not None:
                self.task_registry.complete(fg_task.task_id, result=result)
            return ToolResult.ok(data={"worker_output": result})
        except Exception as e:
            if self.task_registry is not None:
                self.task_registry.fail(fg_task.task_id, error=str(e))
            return ToolResult.fail(f"Worker '{worker_role_name}' failed: {e}")

