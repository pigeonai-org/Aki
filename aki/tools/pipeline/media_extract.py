"""
Pipeline: Media Extract

Deterministic pipeline: audio_extract → audio_vad → transcribe.
Extracts audio from video, performs VAD chunking, then transcribes.
"""

from pathlib import Path
from typing import Any

from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.pipeline._helpers import find_tool
from aki.tools.registry import ToolRegistry


@ToolRegistry.register
class MediaExtractPipelineTool(BaseTool):
    """Extract and transcribe audio from a media file.

    Runs: audio_extract → audio_vad → transcribe.
    Falls back to full-file transcription if VAD fails.
    """

    name: str = "media_extract_pipeline"
    description: str = (
        "Extract audio from a video/audio file, perform voice activity detection, "
        "and transcribe the speech. Returns transcription with timestamps."
    )
    parameters: list[ToolParameter] = [
        ToolParameter(
            name="media_path",
            type="string",
            description="Path to the video or audio file.",
            required=True,
        ),
        ToolParameter(
            name="language",
            type="string",
            description="Language hint for transcription (e.g. 'en', 'zh').",
            required=False,
        ),
        ToolParameter(
            name="provider",
            type="string",
            description="Transcription provider override.",
            required=False,
        ),
        ToolParameter(
            name="model",
            type="string",
            description="Transcription model override.",
            required=False,
        ),
        ToolParameter(
            name="workspace_dir",
            type="string",
            description="Directory for intermediate files. Defaults to 'outputs'.",
            required=False,
        ),
    ]

    def __init__(self, all_tools: list[BaseTool] | None = None) -> None:
        super().__init__()
        self.all_tools: list[BaseTool] = all_tools or []

    async def execute(self, **kwargs: Any) -> ToolResult:
        media_path = str(kwargs.get("media_path") or "").strip()
        if not media_path:
            return ToolResult.fail("media_path is required.")

        audio_extract_tool = find_tool("audio_extract", self.all_tools)
        audio_vad_tool = find_tool("audio_vad", self.all_tools)
        transcribe_tool = find_tool("transcribe", self.all_tools)
        if not all([audio_extract_tool, audio_vad_tool, transcribe_tool]):
            return ToolResult.fail(
                "Pipeline unavailable: missing audio_extract, audio_vad, or transcribe tool."
            )

        workspace = str(kwargs.get("workspace_dir") or "outputs")
        chunks_dir = Path(workspace) / "audio_chunks"
        chunks_dir.mkdir(parents=True, exist_ok=True)

        source_name = Path(media_path).stem
        audio_extract_path = str(Path(workspace).resolve() / f"{source_name}.asr.mp3")

        # Step 1: Extract audio
        extract_result = await audio_extract_tool(
            video_path=media_path, output_path=audio_extract_path,
        )
        if not extract_result.success:
            return ToolResult.fail(f"audio_extract failed: {extract_result.error}")

        audio_path = str((extract_result.data or {}).get("audio_path") or media_path)

        # Step 2: VAD
        vad_result = await audio_vad_tool(audio_path=audio_path, output_dir=str(chunks_dir))

        # Step 3: Transcribe
        language = kwargs.get("language")
        provider = kwargs.get("provider")
        model = kwargs.get("model")

        if not vad_result.success:
            # Fallback: full-file transcription
            transcribe_result = await transcribe_tool(
                audio_path=audio_path, language=language, provider=provider, model=model,
            )
        else:
            data = vad_result.data or {}
            chunk_manifest = []
            if isinstance(data, dict):
                raw_chunks = data.get("chunks") or []
                if isinstance(raw_chunks, list):
                    chunk_manifest = [c for c in raw_chunks if isinstance(c, dict)]
            transcribe_result = await transcribe_tool(
                audio_path=audio_path, language=language, provider=provider,
                model=model, chunks=chunk_manifest or None,
            )

        if not transcribe_result.success:
            return ToolResult.fail(f"transcribe failed: {transcribe_result.error}")

        transcription_data = transcribe_result.data or {}
        if not isinstance(transcription_data, dict):
            return ToolResult.fail("transcribe returned malformed output.")

        return ToolResult.ok(data=transcription_data)
