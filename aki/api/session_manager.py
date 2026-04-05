"""Session manager for persistent multi-turn agent conversations."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from aki.agent.base import UniversalAgent
from aki.agent.orchestrator import AgentOrchestrator, OrchestratorConfig
from aki.agent.state import AgentContext

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    """Tracks a persistent agent session for a user."""

    session_id: str
    user_id: str
    orchestrator: AgentOrchestrator
    agent: Optional[UniversalAgent] = None
    agent_context: Optional[AgentContext] = None
    conversation_history: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_active: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SessionManager:
    """Manages persistent agent sessions for multi-turn conversations.

    Each session keeps a single ``UniversalAgent`` alive across messages so
    the agent can maintain context via conversation history and its memory
    system.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    async def create_session(
        self,
        user_id: str,
        llm_config: str = "openai:gpt-4o",
        extra_tools: list[Any] | None = None,
        auto_load_mcp: bool = True,
        session_id: str | None = None,
        user_context: dict[str, Any] | None = None,
    ) -> SessionState:
        """Create a new persistent session with its own agent.

        Args:
            extra_tools: Additional BaseTool instances (e.g. MCP tools) to
                make available alongside the auto-loaded registry tools.
            auto_load_mcp: If True, automatically discover tools from MCP
                servers configured in ``.aki/mcp.json``.
            session_id: Optional deterministic ID (used by Gateway to
                restore persisted sessions).  Generates a UUID if omitted.
        """
        session_id = session_id or str(uuid4())

        # Auto-discover tools from .aki/mcp.json
        if auto_load_mcp:
            config_tools = await _load_mcp_from_config()
            if config_tools:
                extra_tools = list(extra_tools or []) + config_tools

        llm = _build_llm(llm_config)
        memory = _build_memory(user_id)

        orchestrator = AgentOrchestrator(
            config=OrchestratorConfig(max_iterations=15),
            llm=llm,
            memory=memory,
            auto_load_tools=True,
        )

        # Append extra tools (e.g. MCP bridge tools) so the agent can use them
        if extra_tools:
            orchestrator.tools.extend(extra_tools)

        agent, context = orchestrator.create_session_agent(user_id=user_id)

        if user_context:
            agent.user_context = user_context

        state = SessionState(
            session_id=session_id,
            user_id=user_id,
            orchestrator=orchestrator,
            agent=agent,
            agent_context=context,
        )
        self._sessions[session_id] = state
        return state

    async def send_message(
        self,
        session_id: str,
        message: str,
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Send a message to an existing session and get a response.

        The agent is reused across turns — conversation history is passed to
        ``agent.run_turn()`` so the LLM sees prior context.
        """
        state = self._sessions.get(session_id)
        if not state:
            raise KeyError(f"Session {session_id} not found")

        state.last_active = datetime.now(timezone.utc)

        # Use provided history or the session's accumulated history (copy to avoid aliasing)
        # NOTE: Do NOT append user message here — _build_initial_messages already
        # appends `task` as the final user message. Appending here would duplicate it.
        effective_history = list(history) if history is not None else list(state.conversation_history)

        try:
            if state.agent is not None:
                reply = await state.agent.run_turn(
                    user_message=message,
                    conversation_history=effective_history,
                )
            else:
                # Fallback: no persistent agent (shouldn't happen)
                task = _format_conversational_task(message, effective_history)
                result = await state.orchestrator.run_task(task)
                reply = str(result) if result else "I'm not sure how to respond to that."
        except Exception:
            logger.exception("Error processing message in session %s", session_id)
            reply = "I encountered an internal error. Please try again."

        # Update session history with both user message and reply
        effective_history.append({"role": "user", "content": message})
        effective_history.append({"role": "assistant", "content": reply})
        state.conversation_history = effective_history

        # Post-turn memory review pass
        await self._memory_review(state, effective_history)

        return {
            "reply": reply,
            "system_events": [],
            "profile_updates": {},
            "preference_updates": {},
            "next_status": None,
        }

    async def _memory_review(
        self,
        state: SessionState,
        history: list[dict[str, Any]],
    ) -> None:
        """Run post-turn memory review.

        Uses the new AkiMemorySystem reviewer if available,
        otherwise falls back to the legacy agent-driven review.
        """
        # Try new system first
        if state.agent and getattr(state.agent, "memory_system", None) is not None:
            try:
                memory_system = state.agent.memory_system
                # Only review if enough messages accumulated
                user_msgs = [m for m in history if m.get("role") == "user"]
                if len(user_msgs) < 2:
                    return

                # Run the LLM-powered review pass
                await memory_system.reviewer.review(
                    session_id=memory_system._active_session_id or "",
                    user_id=memory_system.user_id,
                    messages=history,
                    personality_name=memory_system.personality_name,
                    llm=state.agent.llm,
                )
                return
            except Exception:
                import logging
                logging.getLogger(__name__).debug("New review failed, falling back to legacy", exc_info=True)

        # Legacy fallback: let agent call memory_write tool
        try:
            from aki.config.settings import get_settings
            if not get_settings().memory.memory_review_enabled:
                return
        except Exception:
            return

        if state.agent is None:
            return

        review_prompt = (
            "[system]: Review the conversation above. "
            "If any new information worth remembering long-term was shared, "
            "use memory_write to save or update it. "
            "Otherwise just complete with no action."
        )

        review_history = list(history)
        review_history.append({"role": "user", "content": review_prompt})

        saved_callback = getattr(state.agent, "_callback", None)
        saved_memory_system = getattr(state.agent, "memory_system", None)
        state.agent._callback = None
        state.agent.memory_system = None
        try:
            await state.agent.run_turn(
                user_message=review_prompt,
                conversation_history=review_history,
            )
        except Exception:
            pass
        finally:
            state.agent._callback = saved_callback
            state.agent.memory_system = saved_memory_system

    def get_history(self, session_id: str) -> list[dict[str, Any]]:
        """Return conversation history for a session."""
        state = self._sessions.get(session_id)
        if not state:
            raise KeyError(f"Session {session_id} not found")
        return state.conversation_history

    def get_session(self, session_id: str) -> SessionState:
        """Return session state (raises KeyError if not found)."""
        state = self._sessions.get(session_id)
        if not state:
            raise KeyError(f"Session {session_id} not found")
        return state

    def cleanup_session(self, session_id: str) -> None:
        """Remove a session and free its resources."""
        self._sessions.pop(session_id, None)

    def cleanup_idle(self, max_idle_minutes: int = 30) -> int:
        """Remove sessions that have been idle for too long. Returns count removed."""
        now = datetime.now(timezone.utc)
        to_remove = [
            sid
            for sid, state in self._sessions.items()
            if (now - state.last_active).total_seconds() > max_idle_minutes * 60
        ]
        for sid in to_remove:
            self._sessions.pop(sid, None)
        return len(to_remove)

    @property
    def active_count(self) -> int:
        return len(self._sessions)


def _format_conversational_task(message: str, history: list[dict[str, Any]]) -> str:
    """Format a user message + history into a task string for the orchestrator."""
    if not history:
        return message

    lines = []
    for entry in history[-20:]:
        role = entry.get("role") or entry.get("sender_type", "unknown")
        content = entry.get("content", "")
        lines.append(f"[{role}]: {content}")

    context = "\n".join(lines)
    return (
        f"You are in an ongoing conversation. Here is the recent history:\n\n"
        f"{context}\n\n"
        f"The user just said: {message}\n\n"
        f"Respond helpfully and naturally."
    )


def _build_llm(llm_config: str) -> Any:
    """Build an LLM instance from a config string like 'openai:gpt-4o'."""
    try:
        from aki.config.settings import get_settings
        from aki.models.config import ModelConfig
        from aki.models.registry import ModelRegistry
        from aki.models.types.llm import ModelType

        settings = get_settings()
        config = ModelConfig.from_string(llm_config)

        # Resolve API key from settings — matches what CLI _run_task() does
        key_map = {
            "openai": settings.openai_api_key,
            "anthropic": settings.anthropic_api_key,
            "google": settings.google_api_key,
            "qwen": settings.dashscope_api_key,
        }
        config.api_key = key_map.get(config.provider)

        if config.provider == "openai" and settings.openai_base_url:
            config.base_url = settings.openai_base_url

        return ModelRegistry.get(config, ModelType.LLM)
    except Exception:
        return None


def _build_memory(user_id: str) -> Any:  # noqa: ARG001
    """Build a memory manager scoped to a user.

    ``user_id`` is accepted for future per-user namespace isolation but is
    not yet used — all sessions share the global memory namespace for now.
    """
    try:
        from aki.config.settings import get_settings
        from aki.runtime.dependencies import build_memory_manager

        settings = get_settings()
        return build_memory_manager(settings)
    except Exception:
        return None


async def _load_mcp_from_config() -> list[Any]:
    """Discover tools from all MCP servers in ``.aki/mcp.json``."""
    try:
        from aki.mcp.client.adapter import discover_all_configured_tools

        return await discover_all_configured_tools()
    except Exception:
        return []


# Singleton session manager
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
