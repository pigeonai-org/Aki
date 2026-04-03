"""
Memory migration utilities.

Provides helpers for migrating legacy JSON-based memory snapshots into
the new long-term semantic memory store.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from aki.memory.base import MemoryItem
from aki.memory.manager import MemoryManager
from aki.memory.types import MemoryCategory, normalize_category


def _infer_category(item: MemoryItem) -> MemoryCategory:
    """Infer long-term category from legacy memory item."""
    existing = normalize_category(item.category)
    if existing in {
        MemoryCategory.USER_INSTRUCTION,
        MemoryCategory.DOMAIN_KNOWLEDGE,
        MemoryCategory.WEB_KNOWLEDGE,
    }:
        return existing

    item_type = str(item.type or "").strip().lower()
    if item_type in {"user_instruction", "instruction", "preference"}:
        return MemoryCategory.USER_INSTRUCTION
    if item_type in {"domain_knowledge", "domain"}:
        return MemoryCategory.DOMAIN_KNOWLEDGE
    if item_type in {"web_knowledge", "web"}:
        return MemoryCategory.WEB_KNOWLEDGE

    tool_name = str(item.metadata.get("tool") or "").strip().lower()
    if tool_name in {"web_search", "web_read_page"}:
        return MemoryCategory.WEB_KNOWLEDGE

    if item.source_uri:
        return MemoryCategory.WEB_KNOWLEDGE
    if item.metadata.get("instruction_key"):
        return MemoryCategory.USER_INSTRUCTION

    return MemoryCategory.DOMAIN_KNOWLEDGE


def _extract_source_uri(item: MemoryItem) -> Optional[str]:
    if item.source_uri:
        return item.source_uri
    for key in ("url", "source_url", "source_uri"):
        value = item.metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


async def migrate_legacy_json_to_long_term(
    memory_manager: MemoryManager,
    source_file: str,
    *,
    namespace: Optional[str] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Migrate legacy JSON memory file into long-term memory.

    Expected file format: list[dict] where each dict can be parsed by MemoryItem.
    """
    path = Path(source_file).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Memory file not found: {path}")

    raw_data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_data, list):
        raise ValueError("Legacy memory file must contain a JSON array")

    stats = {
        "source_file": str(path),
        "loaded": 0,
        "migrated": 0,
        "skipped_invalid": 0,
        "skipped_empty": 0,
        "dry_run": dry_run,
    }

    target_namespace = namespace or memory_manager.default_namespace

    for raw in raw_data:
        stats["loaded"] += 1
        if not isinstance(raw, dict):
            stats["skipped_invalid"] += 1
            continue

        try:
            item = MemoryItem(**raw)
        except Exception:
            stats["skipped_invalid"] += 1
            continue

        content = str(item.content or "").strip()
        if not content:
            stats["skipped_empty"] += 1
            continue

        category = _infer_category(item)
        metadata = dict(item.metadata)
        if category != item.category:
            metadata["legacy_category"] = getattr(item.category, "value", str(item.category))
        if item.type:
            metadata["legacy_type"] = item.type

        if not dry_run:
            await memory_manager.remember_long_term(
                content=content,
                category=category,
                task_id=item.task_id,
                agent_id=item.agent_id,
                importance=item.importance,
                namespace=target_namespace,
                source_uri=_extract_source_uri(item),
                expires_at=item.expires_at,
                fingerprint=item.fingerprint,
                timestamp=item.timestamp,
                **metadata,
            )

        stats["migrated"] += 1

    return stats
