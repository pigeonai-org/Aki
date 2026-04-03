"""
Audio Extraction Tool

Extracts mono compressed audio from video files via ffmpeg.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.registry import ToolRegistry

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}


@ToolRegistry.register
class AudioExtractTool(BaseTool):
    """Extract audio from media for downstream ASR tasks."""

    name = "audio_extract"
    description = "Extract compressed mono audio from a media file using ffmpeg"
    parameters = [
        ToolParameter(
            name="video_path",
            type="string",
            description="Path to the source video/media file",
        ),
        ToolParameter(
            name="output_path",
            type="string",
            description="Optional output audio path (defaults to <stem>.asr.mp3)",
            required=False,
        ),
    ]

    async def execute(
        self,
        video_path: str,
        output_path: Optional[str] = None,
        sample_rate: int = 16000,
        channels: int = 1,
        bitrate: str = "48k",
        **kwargs: Any,
    ) -> ToolResult:
        """Extract audio track from media file to compressed mp3."""
        del kwargs

        source_path = Path(video_path).expanduser()
        if not source_path.exists():
            return ToolResult.fail(f"Media file not found: {video_path}")

        if source_path.suffix.lower() in AUDIO_EXTENSIONS:
            return ToolResult.ok(
                data={
                    "audio_path": str(source_path),
                    "source_path": str(source_path),
                    "skipped": True,
                }
            )

        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            return ToolResult.fail(
                "ffmpeg not found on PATH. Install ffmpeg to enable audio extraction."
            )

        if output_path:
            target_path = Path(output_path).expanduser()
        else:
            target_path = source_path.with_suffix(".asr.mp3")

        os.makedirs(target_path.parent, exist_ok=True)

        command = [
            ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source_path),
            "-vn",
            "-ac",
            str(channels),
            "-ar",
            str(sample_rate),
            "-b:a",
            bitrate,
            str(target_path),
        ]

        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            return ToolResult.fail(f"ffmpeg extraction failed: {stderr or str(exc)}")

        return ToolResult.ok(
            data={
                "audio_path": str(target_path),
                "source_path": str(source_path),
                "skipped": False,
            }
        )
