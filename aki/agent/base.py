"""
Universal Agent Core

Uses native tool calling — no manual ReACT loop.
The model decides when to call tools and when it's done.
Personality drives identity and behavior; all agents have full tool access.
"""

import json
from typing import Any, Optional, Protocol, runtime_checkable
from uuid import uuid4

from aki.agent.logger import get_agent_logger
from aki.agent.state import AgentContext
from aki.context.manager import ContextManager
from aki.models.types.llm import LLMInterface
from aki.resilience.backoff import RateLimitBackoff
from aki.resilience.recovery import ErrorRecoveryHandler, RecoveryAction
from aki.tools.base import BaseTool, ToolResult
from aki.tools.executor import ToolExecutor, ToolCallRequest
from aki.agent.identity import AgentIdentity
from aki.hooks.engine import HookEngine
from aki.hooks.permission import PermissionEngine
from aki.hooks.rules import PermissionMode
from aki.hooks.types import EventType, HookEvent


@runtime_checkable
class AgentCallback(Protocol):
    """Protocol for receiving real-time agent activity events.

    Implement this to bridge agent execution to a UI, logger, or event bus.
    All methods are async and optional — the agent checks ``callback is not None``
    before each call, so passing None has zero overhead.
    """

    async def on_thinking(self, agent_id: str, iteration: int) -> None:
        """Called before each LLM request."""
        ...

    async def on_tool_start(self, agent_id: str, tool_name: str, params: dict[str, Any]) -> None:
        """Called before a tool begins execution."""
        ...

    async def on_tool_end(self, agent_id: str, tool_name: str, success: bool, duration_ms: float) -> None:
        """Called after a tool completes."""
        ...

    async def on_reply(self, agent_id: str, content: str) -> None:
        """Called when the agent produces a final reply."""
        ...


class AgentError(Exception):
    """Base exception for agent errors."""
    pass


class DepthLimitExceeded(AgentError):
    """Raised when agent depth limit is exceeded."""
    pass


class AgentLimitExceeded(AgentError):
    """Raised when agent count limit is exceeded."""
    pass


class UniversalAgent:
    """
    A unified agent class driven by Personality.

    Uses native tool calling: the LLM decides which tools to call and when to stop.
    No manual observe/think/act/reflect loop needed — modern models handle this natively.
    All agents have full tool access; personality handles identity and behavior.
    """

    def __init__(
        self,
        context: Optional[AgentContext] = None,
        llm: Optional[LLMInterface] = None,
        memory: Optional[Any] = None,
        tools: Optional[list[BaseTool]] = None,
        user_context: Optional[dict[str, Any]] = None,
        context_manager: Optional[ContextManager] = None,
        error_handler: Optional[ErrorRecoveryHandler] = None,
        identity: Optional[AgentIdentity] = None,
        hook_engine: Optional[HookEngine] = None,
        permission_engine: Optional[PermissionEngine] = None,
        callback: Optional[AgentCallback] = None,
        memory_system: Optional[Any] = None,
        agent_name: str = "agent",
    ):
        # AgentIdentity (optional)
        if identity is not None:
            self._identity = identity
            self.agent_name = identity.definition.name
        else:
            self._identity = None
            self.agent_name = agent_name

        self.context = context or AgentContext()
        self.llm = llm  # type: ignore[assignment]
        self.memory = memory
        self.agent_id = identity.agent_id if identity else str(uuid4())
        self.user_context: dict[str, Any] = user_context or {}

        # All tools available — no role-based filtering
        self.tools = list(tools or [])

        # Tool executor for parallel execution (Phase 1)
        self._tool_executor = ToolExecutor()

        # Context management + error recovery (Phase 2, optional)
        self._context_manager = context_manager
        self._error_handler = error_handler
        self._backoff = RateLimitBackoff()

        # Hook + permission system (Phase 4, optional)
        self._hook_engine = hook_engine
        self._permission_engine = permission_engine

        # Real-time callback for UI/renderer (Phase 6, optional)
        self._callback = callback

        # New AkiMemorySystem (optional, coexists with legacy self.memory)
        self.memory_system = memory_system

        # Conversation history for multi-turn sessions (empty = single-shot mode)
        self._conversation_history: list[dict[str, Any]] = []
        self._pending_image_urls: list[str] = []
        self._turn_count: int = 0

    async def run_turn(
        self,
        user_message: str,
        conversation_history: list[dict[str, Any]],
        image_urls: list[str] | None = None,
    ) -> str:
        """Process one user turn within an ongoing conversation."""
        self._conversation_history = conversation_history
        self._pending_image_urls = image_urls or []
        self._turn_count += 1
        result = await self.run(user_message)
        self._pending_image_urls = []
        return str(result) if result else "I'm not sure how to respond to that."

    async def _fire_hook(self, event_type: EventType, **data: Any) -> None:
        """Fire a hook event if a HookEngine is configured (no-op otherwise)."""
        if self._hook_engine is not None:
            event = HookEvent(event_type=event_type, agent_id=self.agent_id, data=data)
            await self._hook_engine.fire(event)

    async def run(self, task: str) -> Any:
        """Native tool calling loop with context management and error recovery.

        When a ContextManager is provided, the loop runs until the token budget
        is exhausted (instead of a hard 20-iteration cap). When an
        ErrorRecoveryHandler is provided, LLM errors are classified and
        recovered automatically (compact, backoff, failover, or abort).
        Both subsystems are optional — without them the agent degrades
        gracefully to a safety cap of 200 iterations.
        """
        logger = get_agent_logger()
        logger.agent_start(self.agent_name, task, self.context.depth)
        logger.indent()

        try:
            # SESSION_START hook
            await self._fire_hook(EventType.SESSION_START, task=task, role=self.agent_name)

            messages = self._build_initial_messages(task)
            self._record_to_session("user", task)
            system_prompt = self._get_system_prompt()
            tool_schemas = [t.to_openai_schema() for t in self.tools] if self.tools else None

            # Allocate token budget if context manager is available
            budget = None
            if self._context_manager is not None:
                sys_tokens = self._context_manager.estimate_tokens(
                    [{"role": "system", "content": system_prompt}]
                )
                schema_tokens = self._context_manager.estimate_tokens(
                    [{"role": "system", "content": json.dumps(tool_schemas or [])}]
                )
                budget = self._context_manager.allocate_budget(
                    system_prompt_tokens=sys_tokens,
                    tool_schemas_tokens=schema_tokens,
                )

            iteration = 0
            max_iterations = 200  # hard safety cap

            while iteration < max_iterations:
                iteration += 1

                # Budget-based loop termination (replaces range(20))
                if budget is not None:
                    msg_tokens = self._context_manager.estimate_tokens(messages)  # type: ignore[union-attr]
                    budget.update_message_tokens(msg_tokens)
                    if not budget.has_capacity():
                        # Attempt compaction before giving up
                        if self._context_manager is not None and self._context_manager.needs_compaction(messages, budget):
                            await self._fire_hook(EventType.CONTEXT_COMPACTION, reason="budget_exhausted_recovery")
                            messages = await self._context_manager.compact(messages, self.llm, budget)
                            # Re-check after compaction
                            msg_tokens = self._context_manager.estimate_tokens(messages)
                            budget.update_message_tokens(msg_tokens)
                        if not budget.has_capacity():
                            logger.dedent()
                            return "Token budget exhausted."

                # --- Callback: thinking ---
                if self._callback is not None:
                    await self._callback.on_thinking(self.agent_id, iteration)

                # --- LLM call with error recovery ---
                try:
                    response = await self.llm.chat(
                        messages=[{"role": "system", "content": system_prompt}] + messages,
                        tools=tool_schemas,
                        max_tokens=4096,
                    )
                    if self._error_handler is not None:
                        self._error_handler.record_success()
                except Exception as e:
                    if self._error_handler is None:
                        raise
                    recovery = self._error_handler.handle_error(e, messages)
                    if recovery.action == RecoveryAction.COMPACT and self._context_manager is not None:
                        messages = await self._context_manager.compact(messages, self.llm, budget)
                        continue
                    elif recovery.action == RecoveryAction.RETRY_BACKOFF:
                        delay = self._backoff._calculate_delay(iteration - 1)
                        import asyncio
                        await asyncio.sleep(delay)
                        continue
                    elif recovery.action == RecoveryAction.FAILOVER:
                        # Failover is handled externally by ModelFailover wrapping self.llm
                        continue
                    else:  # ABORT or unknown
                        logger.dedent()
                        return f"Agent stopped: {recovery.message}"

                # No tool calls → model is done
                if not response.tool_calls:
                    result = response.content
                    self._record_to_session("assistant", str(result or ""))
                    if self._callback is not None:
                        await self._callback.on_reply(self.agent_id, str(result or ""))
                    await self._fire_hook(EventType.SESSION_END, role=self.agent_name, status="complete")
                    logger.dedent()
                    logger.agent_end(self.agent_name, result)
                    return result

                logger.tool_calls(self.agent_name, response.tool_calls)

                # Add assistant message — preserve raw blocks for Anthropic,
                # or raw_tool_calls for OpenAI
                raw_content = response.metadata.get("raw_content")
                raw_tool_calls = response.metadata.get("raw_tool_calls")
                if raw_content is not None:
                    messages.append({"role": "assistant", "content": raw_content})
                elif raw_tool_calls:
                    messages.append({
                        "role": "assistant",
                        "content": response.content or None,
                        "tool_calls": raw_tool_calls,
                    })
                else:
                    messages.append({"role": "assistant", "content": response.content or ""})

                # Callback: tool_start for each call
                if self._callback is not None:
                    for call in response.tool_calls:
                        await self._callback.on_tool_start(self.agent_id, call.name, call.input)

                # PRE_TOOL_USE hooks + permission check
                permitted_calls = []
                for call in response.tool_calls:
                    await self._fire_hook(EventType.PRE_TOOL_USE, tool_name=call.name, tool_params=call.input)
                    # Permission check
                    if self._permission_engine is not None:
                        defn = self._identity.definition if self._identity else None
                        mode = defn.permission_mode if defn else PermissionMode.DEFAULT
                        rules = list(defn.permission_rules) if defn else []
                        allowed = await self._permission_engine.check_permission(
                            self.agent_id, call.name, call.input, mode, rules
                        )
                        if not allowed:
                            # Skip denied tool call, inject a denial result
                            permitted_calls.append(ToolCallRequest(
                                call_id=call.id, tool_name="__denied__", params={"original_tool": call.name}
                            ))
                            continue
                    permitted_calls.append(
                        ToolCallRequest(call_id=call.id, tool_name=call.name, params=call.input)
                    )

                # Execute tool calls via ToolExecutor (parallel for safe tools)
                batch_results = await self._tool_executor.execute_batch(
                    [c for c in permitted_calls if c.tool_name != "__denied__"], self.tools
                )
                # Build results map including denied calls
                denied_results = {
                    c.call_id: ToolResult.fail(f"Permission denied for tool '{c.params.get('original_tool', '?')}'")
                    for c in permitted_calls if c.tool_name == "__denied__"
                }

                tool_result_messages: list[dict[str, Any]] = []
                all_results = {tcr.call_id: tcr.result for tcr in batch_results}
                all_results.update(denied_results)

                for call in response.tool_calls:
                    result = all_results.get(call.id, ToolResult.fail(f"No result for {call.name}"))
                    await self._remember_tool_result(call.name, call.input, result)

                    # POST_TOOL_USE hook + callback
                    tool_success = getattr(result, "success", None)
                    await self._fire_hook(
                        EventType.POST_TOOL_USE, tool_name=call.name,
                        success=tool_success,
                    )
                    if self._callback is not None:
                        await self._callback.on_tool_end(
                            self.agent_id, call.name,
                            success=bool(tool_success),
                            duration_ms=next(
                                (r.duration_ms for r in batch_results if r.call_id == call.id), 0.0
                            ),
                        )

                    result_str = json.dumps(
                        result.model_dump() if hasattr(result, "model_dump") else {"result": str(result)}
                    )

                    if raw_content is not None:
                        tool_result_messages.append({
                            "type": "tool_result",
                            "tool_use_id": call.id,
                            "content": result_str,
                        })
                    else:
                        tool_result_messages.append({
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": result_str,
                        })

                if raw_content is not None:
                    messages.append({"role": "user", "content": tool_result_messages})
                else:
                    messages.extend(tool_result_messages)

                # Context compaction check after tool results
                if self._context_manager is not None and self._context_manager.needs_compaction(messages, budget):
                    await self._fire_hook(EventType.CONTEXT_COMPACTION, reason="threshold_exceeded")
                    messages = await self._context_manager.compact(messages, self.llm, budget)

            logger.dedent()
            return "Maximum iterations reached."

        except Exception as e:
            logger.error(self.agent_name, str(e))
            logger.dedent()
            raise

    async def _remember_tool_result(
        self, tool_name: str, tool_params: dict[str, Any], result: Any
    ) -> None:
        """Best-effort memory persistence for tool results."""
        if self.memory is None or not hasattr(self.memory, "remember"):
            return

        success = getattr(result, "success", None)
        if success is None and isinstance(result, dict):
            success = result.get("success")

        metadata: dict[str, Any] = {"tool": tool_name, "params": tool_params}
        importance = 0.45

        data_payload = getattr(result, "data", None)
        if data_payload is None and isinstance(result, dict):
            data_payload = result.get("data")

        if isinstance(data_payload, dict):
            if "chunked_audio" in data_payload:
                metadata["chunked_audio"] = data_payload.get("chunked_audio")
                importance = max(importance, 0.7)
            if "chunks" in data_payload:
                metadata["chunks"] = data_payload.get("chunks")
                importance = max(importance, 0.7)
            if "segments" in data_payload and isinstance(data_payload.get("segments"), list):
                metadata["segments_count"] = len(data_payload.get("segments") or [])

        error_payload = getattr(result, "error", None)
        if error_payload is None and isinstance(result, dict):
            error_payload = result.get("error")
        if error_payload:
            metadata["error"] = str(error_payload)

        status = "success" if success is not False else "failed"
        content = f"{self.agent_name} tool {tool_name}: {status}"

        if tool_name == "web_search" and success is not False:
            if hasattr(self.memory, "remember_long_term"):
                try:
                    await self.memory.remember_long_term(
                        content=str(data_payload) if data_payload else str(result),
                        category="web_knowledge",
                        task_id=self.context.task_id,
                        agent_id=self.agent_id,
                        importance=0.8,
                        **metadata,
                    )
                except Exception:
                    pass

        if self.memory_system is not None:
            try:
                self.memory_system.append_observation({
                    "type": "tool_result",
                    "tool": tool_name,
                    "success": bool(result and getattr(result, "success", False)),
                    "summary": str(result)[:200],
                })
            except Exception:
                pass

        try:
            await self.memory.remember(
                content=content,
                type="result",
                task_id=self.context.task_id,
                agent_id=self.agent_id,
                importance=importance,
                **metadata,
            )
        except Exception:
            pass

    def _get_system_prompt(self) -> str:
        """Build the system prompt from personality and tools."""
        tool_descriptions = (
            "\n".join(
                f"- {t.name}: {t.description} (params: {', '.join(p.name for p in t.parameters)})"
                for t in self.tools
            )
            or "- None"
        )

        workspace_rule = ""
        if self.context.workspace_dir:
            workspace_rule = (
                f"\nWORKSPACE DIRECTORY:\n"
                f"You are working within an isolated workspace: '{self.context.workspace_dir}'\n"
                f"ALL intermediate outputs, audio files, VAD segments, SRTs, and generated files MUST be saved into this directory.\n"
                f"Do NOT write to the current directory or the video source directory.\n"
            )

        personality_block = self._build_personality_block()
        recall_block = self._build_recall_block()

        return (
            f"{personality_block}"
            f"{recall_block}"
            f"{self._build_user_context_block()}"
            f"\nAVAILABLE TOOLS:\n{tool_descriptions}\n"
            f"{workspace_rule}"
            f"{self._build_memory_index_block()}"
        )

    def _build_recall_block(self) -> str:
        """Inject long-term memory context via the recall pipeline."""
        if self.memory_system is None:
            return ""
        try:
            block = self.memory_system.recall()
            if block:
                return f"\n{block}\n"
        except Exception:
            pass
        return ""

    def _record_to_session(self, role: str, content: str) -> None:
        """Record a message to the active session if memory_system is available."""
        if self.memory_system is not None:
            try:
                self.memory_system.append_message(role, content)
            except Exception:
                pass

    def _build_user_context_block(self) -> str:
        """Render injected user context into the system prompt."""
        if not self.user_context:
            return ""
        ctx = self.user_context
        lines: list[str] = []

        # Core identity
        if ctx.get("user_id"):
            lines.append(f"User ID: {ctx['user_id']}")
        if ctx.get("display_name"):
            lines.append(f"Name: {ctx['display_name']}")
        if ctx.get("date_of_birth"):
            lines.append(f"Date of Birth: {ctx['date_of_birth']}")
        if ctx.get("sex"):
            lines.append(f"Sex: {ctx['sex']}")
        if ctx.get("sexual_orientation"):
            lines.append(f"Sexual Orientation: {ctx['sexual_orientation']}")

        # Location
        location_parts = [p for p in [ctx.get("city"), ctx.get("state_province"), ctx.get("country")] if p]
        if location_parts:
            lines.append(f"Location: {', '.join(location_parts)}")

        # Background
        if ctx.get("occupation"):
            lines.append(f"Occupation: {ctx['occupation']}")
        if ctx.get("education_level"):
            lines.append(f"Education: {ctx['education_level']}")
        if ctx.get("height_cm"):
            lines.append(f"Height: {ctx['height_cm']} cm")
        if ctx.get("bio_short"):
            lines.append(f"Bio: {ctx['bio_short']}")

        # Profile (if available)
        for key, label in [
            ("personality_traits", "Personality Traits"),
            ("interests", "Interests"),
            ("values", "Values"),
            ("lifestyle", "Lifestyle"),
            ("relationship_goals", "Relationship Goals"),
            ("communication_style", "Communication Style"),
        ]:
            val = ctx.get(key)
            if val:
                lines.append(f"{label}: {val}")

        if not lines:
            return ""
        return "\nUSER CONTEXT:\n" + "\n".join(lines) + "\n"

    def _build_memory_index_block(self) -> str:
        """Return a LONG-TERM MEMORY INDEX block for the system prompt."""
        try:
            from aki.tools.memory.index import get_memory_index
            index = get_memory_index()
        except Exception:
            return ""
        if not index:
            return ""
        lines = [f"- {m['name']}: {m['description']}" for m in index]
        return (
            "\nLONG-TERM MEMORY INDEX (use memory_read to load full content):\n"
            + "\n".join(lines)
            + "\n"
        )

    def _build_personality_block(self) -> str:
        """Load active personality + persona memory overlay from the registry."""
        try:
            import json
            from pathlib import Path

            from aki.personality.registry import load_personality

            # Check which personality is active; default to "aki"
            state_file = Path(".aki/personality/active.json")
            name = "aki"  # default persona
            if state_file.exists():
                try:
                    data = json.loads(state_file.read_text(encoding="utf-8"))
                    name = data.get("active") or "aki"
                except (json.JSONDecodeError, OSError):
                    pass

            personality = load_personality(name)
            if personality is None:
                return ""

            # Load persona memory overlay if user context is available
            overlay = ""
            user_id = getattr(self, "_user_id", None) or ""
            if not user_id and self.memory_system is not None:
                user_id = getattr(self.memory_system, "user_id", "")
            if user_id:
                try:
                    from aki.personality.persona_memory.manager import PersonaMemoryManager
                    mgr = PersonaMemoryManager(name, user_id)
                    memory = mgr.load()
                    overlay = memory.to_system_prompt_overlay()
                except Exception:
                    pass

            prompt = personality.to_system_prompt(persona_memory_overlay=overlay)
            if prompt:
                return f"\nPERSONALITY & COMMUNICATION STYLE:\n{prompt}\n"
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Failed to load personality: %s", e)
        return ""

    def _build_initial_messages(self, task: str) -> list[dict[str, Any]]:
        """Build the initial message list, injecting conversation history if present."""
        messages: list[dict[str, Any]] = []
        if self._conversation_history:
            for msg in self._conversation_history[-40:]:
                safe_role = msg.get("role") or msg.get("sender_type", "user")
                if safe_role not in ("user", "assistant"):
                    safe_role = "user"  # remap injected system messages
                content = msg.get("content", "")
                messages.append({"role": safe_role, "content": content})

        # Build the current user message — with image content blocks if present
        image_urls = getattr(self, "_pending_image_urls", [])
        if image_urls:
            # Multimodal message: text + images as content blocks
            # Works with both Anthropic and OpenAI formats
            content_blocks: list[dict[str, Any]] = []
            if task:
                content_blocks.append({"type": "text", "text": task})
            for url in image_urls:
                content_blocks.append({
                    "type": "image",
                    "source": {"type": "url", "url": url},
                })
            messages.append({"role": "user", "content": content_blocks})
        else:
            messages.append({"role": "user", "content": task})

        return messages
