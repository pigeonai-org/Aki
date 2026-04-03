"""
Video Frame Extraction Tool

Extract frames from a video file for vision analysis.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.registry import ToolRegistry


@ToolRegistry.register
class VideoFrameExtractTool(BaseTool):
    """
    Extract frames from a video file.

    Uses ffmpeg if available on the system PATH.
    """

    name = "video_extract_frames"
    description = "Extract frames from a video file for vision analysis"
    parameters = [
        ToolParameter(
            name="video_path",
            type="string",
            description="Path to the video file",
        ),
    ]

    async def execute(
        self,
        video_path: str,
        frame_interval_sec: int = 1,
        max_frames: int = 12,
        output_dir: Optional[str] = None,
        image_format: str = "jpg",
        **kwargs: Any,
    ) -> ToolResult:
        """Extract frames from a video file using ffmpeg."""
        if not os.path.exists(video_path):
            return ToolResult.fail(f"Video file not found: {video_path}")

        if frame_interval_sec < 1:
            return ToolResult.fail("frame_interval_sec must be >= 1")

        if max_frames < 1:
            return ToolResult.fail("max_frames must be >= 1")

        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            return ToolResult.fail(
                "ffmpeg not found on PATH. Install ffmpeg to enable video frame extraction."
            )

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            output_path = output_dir
        else:
            output_path = tempfile.mkdtemp(prefix="aki_frames_")

        output_pattern = os.path.join(output_path, f"frame_%04d.{image_format}")
        fps_filter = f"fps=1/{frame_interval_sec}"

        command = [
            ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            video_path,
            "-vf",
            fps_filter,
            "-vframes",
            str(max_frames),
            "-q:v",
            "2",
            output_pattern,
        ]

        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            error_message = exc.stderr.strip() if exc.stderr else str(exc)
            return ToolResult.fail(f"ffmpeg failed: {error_message}")

        frames = sorted(Path(output_path).glob(f"frame_*.{image_format}"))
        frame_paths = [str(p) for p in frames]

        if not frame_paths:
            return ToolResult.fail("No frames were extracted from the video")

        return ToolResult.ok(
            data={
                "frames": frame_paths,
                "output_dir": output_path,
                "frame_count": len(frame_paths),
            }
        )
