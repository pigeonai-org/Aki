"""
Pipeline: Localize

Deterministic pipeline: subtitle_translate → subtitle_edit.
Translates subtitle segments and optionally polishes the output.
"""

from typing import Any

from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.pipeline._helpers import build_subtitles_from_transcription, find_tool
from aki.tools.registry import ToolRegistry


@ToolRegistry.register
class LocalizePipelineTool(BaseTool):
    """Translate and edit subtitle segments.

    Runs: subtitle_translate → subtitle_edit (optional).
    Accepts raw subtitles or a transcription payload to convert first.
    """

    name: str = "localize_pipeline"
    description: str = (
        "Translate subtitle segments from source language to target language, "
        "then optionally edit/polish the result. Accepts subtitles list or "
        "a transcription dict to auto-convert."
    )
    parameters: list[ToolParameter] = [
        ToolParameter(
            name="subtitles",
            type="array",
            description="List of subtitle dicts with index/start_time/end_time/text.",
            required=False,
        ),
        ToolParameter(
            name="transcription",
            type="object",
            description="Transcription payload (alternative to subtitles). Will be auto-converted.",
            required=False,
        ),
        ToolParameter(
            name="source_language",
            type="string",
            description="Source language code (default: 'en').",
            required=False,
        ),
        ToolParameter(
            name="target_language",
            type="string",
            description="Target language code (default: 'zh').",
            required=False,
        ),
    ]

    def __init__(self, all_tools: list[BaseTool] | None = None) -> None:
        super().__init__()
        self.all_tools: list[BaseTool] = all_tools or []

    async def execute(self, **kwargs: Any) -> ToolResult:
        subtitle_translate_tool = find_tool("subtitle_translate", self.all_tools)
        if subtitle_translate_tool is None:
            return ToolResult.fail("Pipeline unavailable: missing subtitle_translate tool.")
        subtitle_edit_tool = find_tool("subtitle_edit", self.all_tools)

        target_language = str(kwargs.get("target_language") or "zh").strip() or "zh"
        source_language = str(kwargs.get("source_language") or "").strip()

        # Resolve subtitles from various sources
        raw_subtitles = kwargs.get("subtitles")
        subtitles: list[dict[str, Any]] = []
        if isinstance(raw_subtitles, list):
            subtitles = [s for s in raw_subtitles if isinstance(s, dict)]

        if not subtitles:
            transcription = kwargs.get("transcription")
            if transcription is not None:
                subtitles = build_subtitles_from_transcription(transcription)
                if not source_language and isinstance(transcription, dict):
                    source_language = str(transcription.get("language") or "").strip()

        if not subtitles:
            return ToolResult.fail(
                "Requires 'subtitles' list or 'transcription' payload."
            )

        if not source_language:
            source_language = "en"

        # Step 1: Translate
        translate_result = await subtitle_translate_tool(
            subtitles=subtitles,
            source_language=source_language,
            target_language=target_language,
        )
        if not translate_result.success:
            return ToolResult.fail(f"subtitle_translate failed: {translate_result.error}")

        translated_data = translate_result.data or {}
        translated_subtitles: list[dict[str, Any]] = []
        if isinstance(translated_data, dict):
            raw = translated_data.get("subtitles") or []
            if isinstance(raw, list):
                translated_subtitles = [s for s in raw if isinstance(s, dict)]

        if not translated_subtitles:
            return ToolResult.fail("subtitle_translate returned no entries.")

        # Step 2: Edit (optional)
        if subtitle_edit_tool is not None:
            edit_result = await subtitle_edit_tool(subtitles=translated_subtitles)
            if edit_result.success and isinstance(edit_result.data, dict):
                raw_edited = edit_result.data.get("subtitles") or []
                if isinstance(raw_edited, list) and raw_edited:
                    translated_subtitles = [s for s in raw_edited if isinstance(s, dict)]

        # Normalize output
        output: list[dict[str, Any]] = []
        for idx, item in enumerate(translated_subtitles, start=1):
            text = str(item.get("translation") or item.get("text") or "").strip()
            if not text:
                continue
            output.append({
                **item,
                "index": int(item.get("index") or idx),
                "start_time": str(item.get("start_time") or "00:00:00,000"),
                "end_time": str(item.get("end_time") or "00:00:01,000"),
                "text": text,
                "translation": text,
            })

        if not output:
            return ToolResult.fail("Localize pipeline produced empty output.")

        return ToolResult.ok(data={"subtitles": output})
