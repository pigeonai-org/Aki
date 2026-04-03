"""Gateway hub — connects SessionManager, LaneQueue, Persistence, and Platform Adapters.

The Gateway is the central routing layer.  For every inbound message it:

1. Resolves (or creates) a session for the platform + channel.
2. Fires a typing indicator immediately.
3. Acquires the per-session lane lock (serialises concurrent messages).
4. Persists the inbound message to JSONL.
5. Runs context compaction if history is too long.
6. Delegates to ``SessionManager.send_message()``.
7. Persists the assistant reply to JSONL.
8. Returns an ``OutboundMessage`` for the adapter to deliver.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

from aki.api.session_manager import SessionManager
from aki.gateway.adapters.base import PlatformAdapter
from aki.gateway.compaction import ContextCompactor
from aki.gateway.lane_queue import LaneQueue
from aki.gateway.persistence import SessionPersistence
from aki.gateway.types import InboundMessage, OutboundMessage, PlatformContext

logger = logging.getLogger(__name__)


class Gateway:
    """Central message routing hub for multi-platform agent access."""

    def __init__(
        self,
        session_manager: SessionManager,
        persistence: SessionPersistence,
        compactor: ContextCompactor | None = None,
        default_llm: str = "openai:gpt-4o",
    ) -> None:
        self._session_manager = session_manager
        self._persistence = persistence
        self._compactor = compactor
        self._lane_queue = LaneQueue()
        self._adapters: list[PlatformAdapter] = []
        self._adapter_tasks: list[asyncio.Task[None]] = []
        self._default_llm = default_llm

    # ------------------------------------------------------------------
    # Adapter management
    # ------------------------------------------------------------------

    def register_adapter(self, adapter: PlatformAdapter) -> None:
        """Register a platform adapter to be started with the Gateway."""
        self._adapters.append(adapter)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Load persisted state and start all registered adapters."""
        self._persistence.load_index()
        logger.info("Gateway starting with %d adapter(s)", len(self._adapters))

        for adapter in self._adapters:
            task = asyncio.create_task(
                adapter.start(self.handle_message),
                name=f"adapter-{adapter.platform_name}",
            )
            self._adapter_tasks.append(task)

    async def stop(self) -> None:
        """Gracefully shut down all adapters."""
        for adapter in self._adapters:
            try:
                await adapter.stop()
            except Exception as exc:
                logger.warning("Error stopping adapter %s: %s", adapter.platform_name, exc)

        for task in self._adapter_tasks:
            task.cancel()
        self._adapter_tasks.clear()

    # ------------------------------------------------------------------
    # Core message handling
    # ------------------------------------------------------------------

    async def handle_message(self, msg: InboundMessage) -> OutboundMessage:
        """Process one inbound message end-to-end.

        This method is passed as the ``on_message`` callback to adapters.
        """
        session_id = await self._resolve_or_create_session(msg.platform_ctx)

        # Typing indicator fires *before* acquiring the lock so the user
        # sees immediate feedback even while a prior message is processing.
        await self._send_typing(msg.platform_ctx)

        async with self._lane_queue.acquire(session_id):
            # Persist inbound message
            self._persistence.append_entry(session_id, {
                "id": msg.message_id,
                "type": "user",
                "ts": msg.timestamp.isoformat(),
                "platform": msg.platform_ctx.platform,
                "user_id": msg.platform_ctx.user_id,
                "text": msg.text,
            })

            # Compact history if approaching context limit
            await self._maybe_compact(session_id)

            # Delegate to SessionManager
            result = await self._session_manager.send_message(session_id, msg.text)
            reply_text = result.get("reply", "")

            # Persist assistant reply
            reply_id = str(uuid4())
            self._persistence.append_entry(session_id, {
                "id": reply_id,
                "type": "assistant",
                "ts": datetime.now(timezone.utc).isoformat(),
                "text": reply_text,
                "in_reply_to": msg.message_id,
            })

            # Touch index timestamp
            self._persistence.touch_session(
                msg.platform_ctx.platform,
                msg.platform_ctx.channel_id,
            )

            return OutboundMessage(
                text=reply_text,
                session_id=session_id,
                platform_ctx=msg.platform_ctx,
                in_reply_to=msg.message_id,
            )

    # ------------------------------------------------------------------
    # Session resolution
    # ------------------------------------------------------------------

    async def _resolve_or_create_session(self, ctx: PlatformContext) -> str:
        """Find an existing session for this platform+channel, or create one."""
        existing_id = self._persistence.lookup_session(ctx.platform, ctx.channel_id)

        # Session exists and is loaded in memory
        if existing_id and existing_id in self._session_manager._sessions:
            return existing_id

        # Session exists on disk but not in memory — rehydrate
        if existing_id:
            history = self._persistence.rebuild_history(existing_id)
            state = await self._session_manager.create_session(
                user_id=ctx.user_id,
                llm_config=self._default_llm,
                session_id=existing_id,
            )
            state.conversation_history = history
            logger.info("Rehydrated session %s from disk (%d history entries)", existing_id, len(history))
            return existing_id

        # Brand new session
        state = await self._session_manager.create_session(
            user_id=ctx.user_id,
            llm_config=self._default_llm,
        )
        self._persistence.register_session(
            session_id=state.session_id,
            platform=ctx.platform,
            channel_id=ctx.channel_id,
            user_id=ctx.user_id,
            llm_config=self._default_llm,
        )
        logger.info("Created new session %s for %s:%s", state.session_id, ctx.platform, ctx.channel_id)
        return state.session_id

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _send_typing(self, ctx: PlatformContext) -> None:
        """Send a typing indicator via the appropriate adapter."""
        for adapter in self._adapters:
            if adapter.platform_name == ctx.platform:
                try:
                    await adapter.send_typing(ctx)
                except Exception:
                    pass  # Non-critical; best-effort
                break

    async def _maybe_compact(self, session_id: str) -> None:
        """Run context compaction if history exceeds the soft threshold."""
        if self._compactor is None:
            return
        try:
            state = self._session_manager.get_session(session_id)
        except KeyError:
            return
        if self._compactor.needs_compaction(state.conversation_history):
            state.conversation_history = await self._compactor.compact(
                state.conversation_history,
                self._persistence,
                session_id,
            )
