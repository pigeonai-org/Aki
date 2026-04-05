"""
Memory Manager

Coordinates short-term and long-term memory stores with explicit policies for:
- task-scoped short-term working memory
- semantic long-term memory for user/domain/web knowledge
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any, Optional

from aki.memory.base import MemoryItem, MemoryStore, MemoryStrategy
from aki.memory.stores.short_term import ShortTermMemoryStore
from aki.memory.strategies.sliding_window import SlidingWindowStrategy
from aki.memory.types import (
    LONG_TERM_CATEGORIES,
    MemoryCategory,
    MemoryQuery,
    MemoryScope,
    normalize_category,
)


class MemoryManager:
    """
    Memory manager with policy-aware routing between short-term and long-term stores.
    """

    def __init__(
        self,
        short_term: Optional[MemoryStore] = None,
        long_term: Optional[MemoryStore] = None,
        strategy: Optional[MemoryStrategy] = None,
        window_size: int = 20,
        default_namespace: str = "default",
        short_term_observe_limit: int = 12,
        long_term_top_k: int = 6,
        long_term_min_score: float = 0.0,
        web_ttl_days: Optional[int] = 30,
        domain_ttl_days: Optional[int] = None,
        user_instruction_ttl_days: Optional[int] = None,
    ):
        self.short_term = short_term or ShortTermMemoryStore()
        self.long_term = long_term
        self.strategy = strategy or SlidingWindowStrategy(window_size=window_size)

        self.default_namespace = default_namespace
        self.short_term_observe_limit = max(1, short_term_observe_limit)
        self.long_term_top_k = max(1, long_term_top_k)
        self.long_term_min_score = max(0.0, min(1.0, long_term_min_score))

        self.web_ttl_days = web_ttl_days
        self.domain_ttl_days = domain_ttl_days
        self.user_instruction_ttl_days = user_instruction_ttl_days

    @staticmethod
    def _stable_fingerprint(*parts: str) -> str:
        payload = "|".join(parts)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_categories(
        categories: Optional[set[str | MemoryCategory]],
    ) -> Optional[set[MemoryCategory]]:
        if categories is None:
            return None
        normalized = {normalize_category(value) for value in categories}
        return normalized or None

    @staticmethod
    def _compact_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
        """
        Compact heavy payload fields so short-term memory remains lightweight.
        """
        compact: dict[str, Any] = {}
        for key, value in metadata.items():
            if key in {"chunked_audio", "chunks", "segments", "frames", "images"} and isinstance(
                value, list
            ):
                compact[f"{key}_count"] = len(value)
                if len(value) > 20:
                    compact[key] = value[:20]
                    compact[f"{key}_sample"] = value[0]
                else:
                    compact[key] = value
                continue

            if isinstance(value, str) and len(value) > 2000:
                compact[key] = value[:2000] + "...<truncated>"
                continue

            compact[key] = value

        return compact

    @staticmethod
    def _merge_memories(
        primary: list[MemoryItem],
        secondary: list[MemoryItem],
        limit: int,
    ) -> list[MemoryItem]:
        merged: list[MemoryItem] = []
        seen: set[str] = set()
        for item in primary + secondary:
            if item.id in seen:
                continue
            seen.add(item.id)
            merged.append(item)
            if len(merged) >= limit:
                break
        return merged

    def _resolve_expiry(
        self,
        category: MemoryCategory,
        expires_at: Optional[datetime],
    ) -> Optional[datetime]:
        if expires_at is not None:
            return expires_at

        ttl_days: Optional[int]
        if category == MemoryCategory.WEB_KNOWLEDGE:
            ttl_days = self.web_ttl_days
        elif category == MemoryCategory.DOMAIN_KNOWLEDGE:
            ttl_days = self.domain_ttl_days
        elif category == MemoryCategory.USER_INSTRUCTION:
            ttl_days = self.user_instruction_ttl_days
        else:
            ttl_days = None

        if ttl_days is None:
            return None
        return datetime.now() + timedelta(days=ttl_days)

    async def remember(
        self,
        content: str,
        type: str,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        importance: float = 0.5,
        **metadata: Any,
    ) -> MemoryItem:
        """
        Backward-compatible API: remember into short-term memory.
        """
        return await self.remember_short_term(
            content=content,
            type=type,
            task_id=task_id,
            agent_id=agent_id,
            importance=importance,
            **metadata,
        )

    async def remember_short_term(
        self,
        content: str,
        *,
        category: Optional[str | MemoryCategory] = None,
        type: Optional[str] = None,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        importance: float = 0.5,
        namespace: Optional[str] = None,
        modality: Optional[str] = None,
        **metadata: Any,
    ) -> MemoryItem:
        """
        Persist memory to short-term task-scoped storage.
        """
        resolved_category = normalize_category(category or type)
        compact_metadata = self._compact_metadata(metadata)

        if modality:
            compact_metadata["modality"] = modality

        if resolved_category in {
            MemoryCategory.TASK_EVENT,
            MemoryCategory.OBSERVATION,
            MemoryCategory.RESULT,
        } and any(
            key in metadata for key in ("chunked_audio", "chunks", "segments", "frames", "images")
        ):
            resolved_category = MemoryCategory.MULTIMODAL_ARTIFACT

        item = MemoryItem(
            content=content,
            type=type or resolved_category.value,
            category=resolved_category,
            scope=MemoryScope.SHORT_TERM,
            task_id=task_id,
            agent_id=agent_id,
            importance=importance,
            namespace=namespace or self.default_namespace,
            metadata=compact_metadata,
        )
        await self.short_term.add(item)
        return item

    async def remember_long_term(
        self,
        content: str,
        *,
        category: str | MemoryCategory,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        importance: float = 0.7,
        namespace: Optional[str] = None,
        source_uri: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        fingerprint: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        type: Optional[str] = None,
        **metadata: Any,
    ) -> MemoryItem:
        """
        Persist semantic memory for long-term retrieval.
        """
        resolved_category = normalize_category(category, default=MemoryCategory.DOMAIN_KNOWLEDGE)
        if resolved_category not in LONG_TERM_CATEGORIES:
            raise ValueError(
                "Long-term memory category must be one of: "
                "user_instruction, domain_knowledge, web_knowledge"
            )

        resolved_namespace = namespace or self.default_namespace
        resolved_expiry = self._resolve_expiry(resolved_category, expires_at)

        resolved_fingerprint = fingerprint
        if resolved_fingerprint is None and source_uri:
            resolved_fingerprint = self._stable_fingerprint(
                resolved_namespace,
                resolved_category.value,
                source_uri,
            )
        if resolved_fingerprint is None:
            resolved_fingerprint = self._stable_fingerprint(
                resolved_namespace,
                resolved_category.value,
                content.strip()[:512],
            )

        item = MemoryItem(
            content=content,
            type=type or resolved_category.value,
            category=resolved_category,
            scope=MemoryScope.LONG_TERM,
            timestamp=timestamp or datetime.now(),
            task_id=task_id,
            agent_id=agent_id,
            importance=importance,
            namespace=resolved_namespace,
            source_uri=source_uri,
            expires_at=resolved_expiry,
            fingerprint=resolved_fingerprint,
            metadata=metadata,
        )

        if self.long_term is not None:
            await self.long_term.add(item)
        return item

    async def upsert_user_instruction(
        self,
        key: str,
        content: str,
        *,
        namespace: Optional[str] = None,
        source_uri: Optional[str] = None,
        **metadata: Any,
    ) -> MemoryItem:
        """
        Upsert user instruction memory with stable fingerprinting.
        """
        resolved_namespace = namespace or self.default_namespace
        fingerprint = self._stable_fingerprint(
            resolved_namespace,
            MemoryCategory.USER_INSTRUCTION.value,
            key,
        )
        return await self.remember_long_term(
            content=content,
            category=MemoryCategory.USER_INSTRUCTION,
            namespace=resolved_namespace,
            source_uri=source_uri,
            fingerprint=fingerprint,
            instruction_key=key,
            **metadata,
        )

    async def recall(
        self,
        query: Optional[str] = None,
        limit: int = 10,
        task_id: Optional[str] = None,
    ) -> list[MemoryItem]:
        """
        Backward-compatible API: recall from short-term memory.
        """
        return await self.recall_short_term(query=query, limit=limit, task_id=task_id)

    async def recall_short_term(
        self,
        *,
        query: Optional[str] = None,
        limit: Optional[int] = None,
        task_id: Optional[str] = None,
        categories: Optional[set[str | MemoryCategory]] = None,
    ) -> list[MemoryItem]:
        """
        Recall task-scoped short-term memory.
        """
        effective_limit = limit or self.short_term_observe_limit
        normalized_categories = self._normalize_categories(categories)
        memory_query = MemoryQuery(
            query=query,
            limit=effective_limit,
            task_id=task_id,
            categories=normalized_categories,
            scope=MemoryScope.SHORT_TERM,
        )

        store_recall = getattr(self.short_term, "recall", None)
        if callable(store_recall):
            items = await store_recall(memory_query)
            return items[:effective_limit]

        # Fallback for legacy short-term stores.
        if task_id:
            task_memories = await self.short_term.get_by_task(task_id)
            selected = self.strategy.select(task_memories, effective_limit)
        elif query:
            selected = await self.short_term.search(query, effective_limit)
        else:
            selected = await self.short_term.get_recent(effective_limit)

        if normalized_categories:
            selected = [item for item in selected if item.category in normalized_categories]
        return selected[:effective_limit]

    async def recall_long_term(
        self,
        *,
        query: Optional[str] = None,
        limit: Optional[int] = None,
        categories: Optional[set[str | MemoryCategory]] = None,
        namespace: Optional[str] = None,
        min_score: Optional[float] = None,
        include_expired: bool = False,
    ) -> list[MemoryItem]:
        """
        Recall semantic long-term memory.
        """
        if self.long_term is None:
            return []

        effective_limit = limit or self.long_term_top_k
        normalized_categories = self._normalize_categories(categories)
        memory_query = MemoryQuery(
            query=query,
            limit=effective_limit,
            namespace=namespace or self.default_namespace,
            categories=normalized_categories,
            scope=MemoryScope.LONG_TERM,
            min_score=self.long_term_min_score if min_score is None else min_score,
            include_expired=include_expired,
        )

        semantic_search = getattr(self.long_term, "search_semantic", None)
        if callable(semantic_search):
            items = await semantic_search(memory_query)
            return items[:effective_limit]

        # Fallback for legacy long-term stores.
        if query:
            items = await self.long_term.search(query, effective_limit)
        else:
            items = await self.long_term.get_recent(effective_limit)

        if normalized_categories:
            items = [item for item in items if item.category in normalized_categories]
        if not include_expired:
            now = datetime.now()
            items = [item for item in items if item.expires_at is None or item.expires_at > now]
        return items[:effective_limit]

    async def recall_context(
        self,
        *,
        task_id: str,
        query: Optional[str] = None,
        namespace: Optional[str] = None,
        short_term_limit: Optional[int] = None,
        long_term_limit: Optional[int] = None,
        long_term_categories: Optional[set[str | MemoryCategory]] = None,
        min_score: Optional[float] = None,
    ) -> dict[str, list[MemoryItem]]:
        """
        Retrieve fused memory context for an agent observation.
        """
        short_limit = short_term_limit or self.short_term_observe_limit
        long_limit = long_term_limit or self.long_term_top_k
        effective_long_categories = long_term_categories or {
            MemoryCategory.USER_INSTRUCTION,
            MemoryCategory.DOMAIN_KNOWLEDGE,
            MemoryCategory.WEB_KNOWLEDGE,
        }

        recent_short_term = await self.recall_short_term(
            query=None,
            limit=short_limit,
            task_id=task_id,
        )
        if query:
            matched_short_term = await self.recall_short_term(
                query=query,
                limit=short_limit,
                task_id=task_id,
            )
            short_term_context = self._merge_memories(
                matched_short_term,
                recent_short_term,
                short_limit,
            )
        else:
            short_term_context = recent_short_term

        long_term_context = await self.recall_long_term(
            query=query,
            limit=long_limit,
            categories=effective_long_categories,
            namespace=namespace,
            min_score=min_score,
        )

        combined = short_term_context + long_term_context
        return {
            "short_term": short_term_context,
            "long_term": long_term_context,
            "combined": combined,
        }

    async def promote(
        self,
        *,
        task_id: Optional[str] = None,
        min_importance: float = 0.7,
        categories: Optional[set[str | MemoryCategory]] = None,
        namespace: Optional[str] = None,
    ) -> int:
        """
        Promote selected short-term memories to long-term storage.
        """
        if self.long_term is None:
            return 0

        normalized_categories = self._normalize_categories(categories)
        candidates = await self.recall_short_term(
            task_id=task_id,
            limit=1000,
            categories=categories,
        )

        promoted = 0
        for memory in candidates:
            if memory.importance < min_importance:
                continue
            if normalized_categories and memory.category not in normalized_categories:
                continue
            if memory.category not in LONG_TERM_CATEGORIES:
                continue

            await self.remember_long_term(
                content=memory.content,
                category=memory.category,
                task_id=memory.task_id,
                agent_id=memory.agent_id,
                importance=memory.importance,
                namespace=namespace or memory.namespace,
                source_uri=memory.source_uri,
                fingerprint=memory.fingerprint,
                **memory.metadata,
            )
            promoted += 1

        return promoted

    async def consolidate(self) -> int:
        """
        Backward-compatible alias of promote().
        """
        return await self.promote(min_importance=0.7)

    async def prune_long_term(self, now: Optional[datetime] = None) -> int:
        """
        Prune expired long-term memories by TTL policy.
        """
        if self.long_term is None:
            return 0
        prune_func = getattr(self.long_term, "prune_expired", None)
        if callable(prune_func):
            return await prune_func(now)
        return 0

    async def clear_short_term(self) -> None:
        """Clear short-term memory."""
        await self.short_term.clear()

    async def clear_all(self) -> None:
        """Clear short-term and long-term memory."""
        await self.short_term.clear()
        if self.long_term:
            await self.long_term.clear()

    async def get_stats(self) -> dict[str, Any]:
        """Get memory statistics."""
        stats: dict[str, Any] = {
            "short_term_count": await self.short_term.count(),
            "long_term_enabled": self.long_term is not None,
            "default_namespace": self.default_namespace,
        }
        if self.long_term:
            stats["long_term_count"] = await self.long_term.count()
        return stats


# Global memory manager instance
_memory_manager: Optional[MemoryManager] = None


def get_memory_manager() -> MemoryManager:
    """Get the global memory manager instance (singleton)."""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager


def reset_memory_manager() -> None:
    """Reset the global memory manager instance (useful for testing)."""
    global _memory_manager
    _memory_manager = None


class AkiMemorySystem:
    """
    Unified memory system orchestrating all 4 layers:
        Layer 0: Working Memory (context window — managed externally)
        Layer 1: Session Memory (persistent per-session)
        Layer 2: Long-term Memory (5 dimensions)
        Layer 3: Core Memory (personality — managed externally)
    """

    def __init__(
        self,
        user_id: str = "",
        personality_name: str = "aki",
        session_store: Any = None,
        user_store: Any = None,
        episodic_store: Any = None,
        semantic_store: Any = None,
        procedural_store: Any = None,
        persona_bridge: Any = None,
        legacy_manager: MemoryManager | None = None,
    ):
        from aki.memory.session.store import SessionStore, get_session_store
        from aki.memory.dimensions.user import UserMemoryStore
        from aki.memory.dimensions.episodic import EpisodicMemoryStore
        from aki.memory.dimensions.semantic import SemanticMemoryStore
        from aki.memory.dimensions.procedural import ProceduralMemoryStore
        from aki.memory.dimensions.persona import PersonaDimensionBridge
        from aki.memory.recall import RecallPipeline
        from aki.memory.review import MemoryReviewer

        self.user_id = user_id
        self.personality_name = personality_name

        # Layer 1: Session
        self.session_store = session_store or get_session_store()

        # Layer 2: Dimensions
        self.user_store = user_store or UserMemoryStore()
        self.episodic_store = episodic_store or EpisodicMemoryStore(personality_name=personality_name)
        self.semantic_store = semantic_store or SemanticMemoryStore()
        self.procedural_store = procedural_store or ProceduralMemoryStore()
        self.persona_bridge = persona_bridge or PersonaDimensionBridge(personality_name)

        # Pipelines
        self.recall_pipeline = RecallPipeline(
            user_store=self.user_store,
            episodic_store=self.episodic_store,
            semantic_store=self.semantic_store,
            procedural_store=self.procedural_store,
            persona_bridge=self.persona_bridge,
        )
        self.reviewer = MemoryReviewer(
            user_store=self.user_store,
            episodic_store=self.episodic_store,
            procedural_store=self.procedural_store,
            persona_bridge=self.persona_bridge,
        )

        # Legacy compatibility
        self.legacy = legacy_manager or MemoryManager()

        # Active session tracking
        self._active_session_id: str | None = None

    # ── Session lifecycle ──

    def start_session(self, session_id: str | None = None, tags: list[str] | None = None):
        """Start a new session or resume an existing one."""
        if session_id:
            session = self.session_store.resume(session_id)
            if session:
                self._active_session_id = session.session_id
                return session

        session = self.session_store.create(
            user_id=self.user_id,
            personality_name=self.personality_name,
            session_id=session_id,
            tags=tags,
        )
        self._active_session_id = session.session_id
        return session

    def end_session(self, session_id: str | None = None) -> None:
        """End a session — suspend it (keeps on disk for potential resume)."""
        sid = session_id or self._active_session_id
        if sid:
            self.session_store.suspend(sid)
            if sid == self._active_session_id:
                self._active_session_id = None

    async def end_session_with_review(
        self, session_id: str | None = None, llm: Any = None,
    ):
        """End a session with a full memory review pass."""
        from aki.memory.review import ReviewResult

        sid = session_id or self._active_session_id
        if not sid:
            return ReviewResult(skipped=True, skip_reason="No active session")

        session = self.session_store.get(sid)
        if not session:
            session = self.session_store.resume(sid)
        if not session:
            return ReviewResult(skipped=True, skip_reason=f"Session {sid} not found")

        # Run review
        result = await self.reviewer.review(
            session_id=sid,
            user_id=self.user_id,
            messages=session.messages,
            personality_name=self.personality_name,
            llm=llm,
        )

        # Archive the session
        self.session_store.archive(sid, summary=result.episodic_summary)
        if sid == self._active_session_id:
            self._active_session_id = None

        return result

    # ── Recall ──

    def recall(self, query: str = "") -> str:
        """Run the full recall pipeline and return the context block for system prompt injection."""
        if not self.user_id:
            return ""
        result = self.recall_pipeline.recall(user_id=self.user_id, query=query)
        return result.to_system_prompt_block()

    # ── Session write helpers ──

    def append_message(self, role: str, content: str, **extra) -> None:
        """Append a message to the active session."""
        if self._active_session_id:
            self.session_store.append_message(self._active_session_id, role, content, **extra)

    def append_observation(self, observation: dict) -> None:
        """Append an observation to the active session."""
        if self._active_session_id:
            self.session_store.append_observation(self._active_session_id, observation)

    # ── Direct dimension access ──

    def get_user_profile(self) -> dict:
        """Get the user's profile from user memory."""
        if not self.user_id:
            return {}
        return self.user_store.load(self.user_id)

    def add_user_fact(self, fact: str) -> None:
        """Add a fact to user memory."""
        if self.user_id:
            self.user_store.add_fact(self.user_id, fact)

    def add_procedural_rule(self, rule: str, confidence: float = 0.8, source: str = "") -> None:
        """Add a work preference rule."""
        if self.user_id:
            self.procedural_store.add_rule(self.user_id, rule, confidence, source)

    def get_recent_episodes(self, limit: int = 5) -> list:
        """Get recent episodic memories."""
        if not self.user_id:
            return []
        return self.episodic_store.get_recent(self.user_id, limit=limit)


# ── Global singleton for new system ──

_aki_memory: AkiMemorySystem | None = None


def get_aki_memory(user_id: str = "", personality_name: str = "aki") -> AkiMemorySystem:
    """Get the global AkiMemorySystem instance."""
    global _aki_memory
    if _aki_memory is None or (_aki_memory.user_id != user_id and user_id):
        _aki_memory = AkiMemorySystem(user_id=user_id, personality_name=personality_name)
    return _aki_memory


def reset_aki_memory() -> None:
    """Reset the global AkiMemorySystem (for testing)."""
    global _aki_memory
    _aki_memory = None
