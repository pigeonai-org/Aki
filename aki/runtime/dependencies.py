"""Runtime factory helpers for dependency wiring."""

from typing import Any

from aki.config.settings import MemorySettings, Settings
from aki.memory import MemoryManager
from aki.memory.stores.short_term import ShortTermMemoryStore


def _resolve_memory_settings(settings: Any) -> MemorySettings:
    raw_memory_settings = getattr(settings, "memory", None)
    if isinstance(raw_memory_settings, MemorySettings):
        return raw_memory_settings
    if raw_memory_settings is None:
        return MemorySettings()
    try:
        return MemorySettings.model_validate(raw_memory_settings)
    except Exception:
        return MemorySettings()


def build_memory_manager(settings: Settings) -> MemoryManager:
    """
    Build a configured MemoryManager from application settings.

    Long-term memory is handled by the Markdown-based memory tools
    (memory_write / memory_read / memory_list) that agents call directly.
    The MemoryManager only manages short-term working memory.
    """
    memory_settings = _resolve_memory_settings(settings)
    max_size = max(
        memory_settings.short_term_max_items_per_task * 10,
        memory_settings.window_size * 20,
    )
    short_term = ShortTermMemoryStore(
        max_size=max_size,
        max_items_per_task=memory_settings.short_term_max_items_per_task,
    )

    return MemoryManager(
        short_term=short_term,
        long_term=None,
        window_size=memory_settings.window_size,
        default_namespace=memory_settings.default_namespace,
        short_term_observe_limit=memory_settings.short_term_observe_limit,
    )
