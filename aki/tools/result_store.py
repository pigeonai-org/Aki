"""
Large Result Store

Stores tool results that exceed a size threshold to disk.
Returns a file path + preview to keep the LLM context window small.
"""

import json
import logging
import os
import time
from typing import Any

from aki.tools.base import ToolResult

logger = logging.getLogger(__name__)


class LargeResultStore:
    """
    Stores tool results exceeding a threshold to disk.

    When a ToolResult's data serializes to more than ``threshold_chars``,
    the full result is written to disk and replaced with a truncated preview
    plus the file path.

    Usage::

        store = LargeResultStore(base_dir=".aki/tool_results")
        result = await tool(**params)
        result = await store.store_if_large(result, tool_name="web_search")
    """

    def __init__(
        self,
        base_dir: str = ".aki/tool_results",
        threshold_chars: int = 50_000,
        preview_chars: int = 2_000,
    ) -> None:
        self.base_dir = base_dir
        self.threshold_chars = threshold_chars
        self.preview_chars = preview_chars

    async def store_if_large(self, result: ToolResult, tool_name: str) -> ToolResult:
        """
        Check result size and store to disk if it exceeds the threshold.

        Args:
            result: The tool result to potentially store.
            tool_name: Name of the tool (used in filename).

        Returns:
            Original result if small enough, or a modified result with
            a preview and file path reference.
        """
        if not result.success or result.data is None:
            return result

        # Serialize data to check size
        try:
            serialized = json.dumps(result.data, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            serialized = str(result.data)

        if len(serialized) <= self.threshold_chars:
            return result

        # Store to disk
        os.makedirs(self.base_dir, exist_ok=True)
        filename = f"{tool_name}_{int(time.time() * 1000)}.json"
        filepath = os.path.join(self.base_dir, filename)

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(serialized)
        except OSError:
            logger.warning("Failed to write large result to %s", filepath)
            return result

        preview = serialized[: self.preview_chars]
        logger.info(
            "Stored large result for %s (%d chars) to %s",
            tool_name,
            len(serialized),
            filepath,
        )

        return ToolResult(
            success=True,
            data={
                "_stored": True,
                "_path": filepath,
                "_size": len(serialized),
                "_preview": preview,
            },
            error=None,
            metadata={
                **result.metadata,
                "stored_path": filepath,
                "original_size": len(serialized),
            },
        )

    async def retrieve(self, result_path: str) -> Any:
        """
        Retrieve a previously stored result from disk.

        Args:
            result_path: Path to the stored result file.

        Returns:
            Deserialized result data.
        """
        resolved = os.path.realpath(result_path)
        base_resolved = os.path.realpath(self.base_dir)
        if not resolved.startswith(base_resolved + os.sep) and resolved != base_resolved:
            raise ValueError(f"Path '{result_path}' is outside the allowed directory")
        with open(resolved, encoding="utf-8") as f:
            return json.load(f)

    def cleanup(self, max_age_seconds: int = 86400) -> int:
        """
        Remove stored results older than max_age.

        Returns:
            Number of files removed.
        """
        if not os.path.isdir(self.base_dir):
            return 0

        now = time.time()
        removed = 0
        for filename in os.listdir(self.base_dir):
            filepath = os.path.join(self.base_dir, filename)
            try:
                if now - os.path.getmtime(filepath) > max_age_seconds:
                    os.remove(filepath)
                    removed += 1
            except OSError:
                pass
        return removed
