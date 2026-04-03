"""
Pipeline: QA Edit

Deterministic pipeline: subtitle_proofread → srt_write.
Proofreads translated subtitles and writes the final SRT file.
"""

from pathlib import Path
from typing import Any

from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.pipeline._helpers import find_tool
from aki.tools.registry import ToolRegistry


@ToolRegistry.register
class QAEditPipelineTool(BaseTool):
    """Proofread translated subtitles and write the final SRT file.

    Runs: subtitle_proofread → srt_write.
    Can also read subtitles from an existing SRT file.
    """

    name: str = "qa_edit_pipeline"
    description: str = (
        "Proofread translated subtitles for quality assurance, "
        "then write the final SRT file to disk."
    )
    parameters: list[ToolParameter] = [
        ToolParameter(
            name="subtitles",
            type="array",
            description="List of translated subtitle dicts.",
            required=False,
        ),
        ToolParameter(
            name="subtitle_file_path",
            type="string",
            description="Path to an existing SRT file to read subtitles from (alternative to subtitles).",
            required=False,
        ),
        ToolParameter(
            name="output_path",
            type="string",
            description="Output SRT file path. Defaults to workspace_dir/final_subtitles.srt.",
            required=False,
        ),
        ToolParameter(
            name="target_language",
            type="string",
            description="Target language for proofreading context (default: 'zh').",
            required=False,
        ),
        ToolParameter(
            name="workspace_dir",
            type="string",
            description="Workspace directory for output. Defaults to 'outputs'.",
            required=False,
        ),
    ]

    def __init__(self, all_tools: list[BaseTool] | None = None) -> None:
        super().__init__()
        self.all_tools: list[BaseTool] = all_tools or []

    async def execute(self, **kwargs: Any) -> ToolResult:
        proofread_tool = find_tool("subtitle_proofread", self.all_tools)
        srt_write_tool = find_tool("srt_write", self.all_tools)
        if proofread_tool is None or srt_write_tool is None:
            return ToolResult.fail(
                "Pipeline unavailable: missing subtitle_proofread or srt_write tool."
            )

        # Resolve subtitles
        raw_subs = kwargs.get("subtitles")
        subtitles: list[dict[str, Any]] = []
        if isinstance(raw_subs, list):
            subtitles = [s for s in raw_subs if isinstance(s, dict)]

        # Fallback: read from SRT file
        subtitle_file_path = kwargs.get("subtitle_file_path")
        if not subtitles and subtitle_file_path:
            srt_read_tool = find_tool("srt_read", self.all_tools)
            if srt_read_tool is not None:
                read_result = await srt_read_tool(file_path=str(subtitle_file_path))
                if read_result.success and isinstance(read_result.data, dict):
                    raw = read_result.data.get("subtitles") or []
                    if isinstance(raw, list):
                        subtitles = [s for s in raw if isinstance(s, dict)]

        if not subtitles:
            return ToolResult.fail(
                "Requires 'subtitles' list or a readable 'subtitle_file_path'."
            )

        # Step 1: Proofread
        target_language = str(kwargs.get("target_language") or "zh").strip() or "zh"
        proofread_result = await proofread_tool(
            subtitles=subtitles,
            target_language=target_language,
            context="QA pass for subtitle translation workflow.",
        )

        reviewed = subtitles
        if proofread_result.success and isinstance(proofread_result.data, dict):
            raw_reviewed = proofread_result.data.get("subtitles") or []
            if isinstance(raw_reviewed, list) and raw_reviewed:
                reviewed = [s for s in raw_reviewed if isinstance(s, dict)]

        # Step 2: Write SRT
        output_path = kwargs.get("output_path")
        if not output_path:
            workspace = str(kwargs.get("workspace_dir") or "outputs")
            output_path = str(Path(workspace).resolve() / "final_subtitles.srt")

        write_result = await srt_write_tool(
            file_path=str(output_path),
            subtitles=reviewed,
            prefer_translation=True,
        )
        if not write_result.success:
            return ToolResult.fail(f"srt_write failed: {write_result.error}")

        return ToolResult.ok(data={"output_path": str(output_path), "subtitle_count": len(reviewed)})
