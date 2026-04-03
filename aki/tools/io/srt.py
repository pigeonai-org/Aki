"""
SRT Subtitle Tool

Read and write SRT subtitle files.
Pure executor - no decision making.
"""

from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.registry import ToolRegistry


class SubtitleEntry(BaseModel):
    """A single subtitle entry."""

    index: int = Field(..., description="Subtitle index")
    start_time: str = Field(..., description="Start time (HH:MM:SS,mmm)")
    end_time: str = Field(..., description="End time (HH:MM:SS,mmm)")
    text: str = Field(..., description="Subtitle text (source or target)")
    src_text: Optional[str] = Field(None, description="Source text")
    translation: Optional[str] = Field(None, description="Translated text")


@ToolRegistry.register
class SRTReadTool(BaseTool):
    """
    SRT file reader tool.

    Reads and parses SRT subtitle files.
    """

    name = "srt_read"
    description = "Read and parse SRT subtitle file"
    parameters = [
        ToolParameter(
            name="file_path",
            type="string",
            description="Path to the SRT file",
        ),
    ]
    concurrency_safe = True

    async def execute(
        self,
        file_path: str,
        **kwargs: Any,
    ) -> ToolResult:
        """
        Read SRT file.

        Args:
            file_path: Path to SRT file

        Returns:
            ToolResult with parsed subtitles
        """
        try:
            path = Path(file_path)
            if not path.exists():
                return ToolResult.fail(f"File not found: {file_path}")

            content = path.read_text(encoding="utf-8")
            subtitles = self._parse_srt(content)

            return ToolResult.ok(
                data={
                    "subtitles": [s.model_dump() for s in subtitles],
                    "count": len(subtitles),
                },
                file_path=file_path,
            )
        except Exception as e:
            return ToolResult.fail(f"Failed to read SRT: {str(e)}")

    def _parse_srt(self, content: str) -> list[SubtitleEntry]:
        """Parse SRT content into subtitle entries."""
        subtitles = []
        blocks = content.strip().split("\n\n")

        for block in blocks:
            lines = block.strip().split("\n")
            if len(lines) >= 3:
                try:
                    index = int(lines[0])
                    times = lines[1].split(" --> ")
                    text = "\n".join(lines[2:])
                    subtitles.append(
                        SubtitleEntry(
                            index=index,
                            start_time=times[0].strip(),
                            end_time=times[1].strip(),
                            text=text,
                            src_text=text,  # Assume text is source initially
                        )
                    )
                except (ValueError, IndexError):
                    continue

        return subtitles


@ToolRegistry.register
class SRTWriteTool(BaseTool):
    """
    SRT file writer tool.

    Writes subtitles to SRT format.
    """

    name = "srt_write"
    description = "Write subtitles to SRT file"
    parameters = [
        ToolParameter(
            name="file_path",
            type="string",
            description="Output file path",
        ),
        ToolParameter(
            name="subtitles",
            type="array",
            description="List of subtitle entries",
        ),
        ToolParameter(
            name="prefer_translation",
            type="boolean",
            description="If true, write translation instead of text",
            required=False,
        ),
    ]

    async def execute(
        self,
        file_path: str,
        subtitles: list[dict[str, Any]],
        prefer_translation: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """
        Write SRT file.

        Args:
            file_path: Output path
            subtitles: List of subtitle dicts
            prefer_translation: Write translation field if available

        Returns:
            ToolResult with status
        """
        try:
            content = self._generate_srt(subtitles, prefer_translation)
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

            return ToolResult.ok(
                data={
                    "file_path": file_path,
                    "count": len(subtitles),
                },
            )
        except Exception as e:
            return ToolResult.fail(f"Failed to write SRT: {str(e)}")

    def _generate_srt(self, subtitles: list[dict[str, Any]], prefer_translation: bool) -> str:
        """Generate SRT content from subtitle entries."""
        lines = []
        for i, sub in enumerate(subtitles, 1):
            index = sub.get("index", i)
            start = sub.get("start_time", "00:00:00,000")
            end = sub.get("end_time", "00:00:01,000")

            if prefer_translation and sub.get("translation"):
                text = sub.get("translation", "")
            else:
                text = sub.get("text", "")

            lines.append(str(index))
            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")

        return "\n".join(lines)
