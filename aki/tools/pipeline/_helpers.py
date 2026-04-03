"""Shared helpers for pipeline tools."""

from typing import Any

from aki.tools.base import BaseTool


def find_tool(tool_name: str, tools: list[BaseTool]) -> BaseTool | None:
    """Look up a tool by name from a tool list."""
    for tool in tools:
        if tool.name == tool_name:
            return tool
    return None


def to_float(value: Any) -> float | None:
    """Best-effort float conversion."""
    try:
        return float(value)
    except Exception:
        return None


def seconds_to_srt(seconds: float) -> str:
    """Convert seconds to SRT timestamp HH:MM:SS,mmm."""
    total_ms = max(0, int(round(float(seconds) * 1000)))
    hours = total_ms // 3600000
    total_ms %= 3600000
    minutes = total_ms // 60000
    total_ms %= 60000
    secs = total_ms // 1000
    millis = total_ms % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def extract_media_path(context_data: dict[str, Any]) -> str | None:
    """Best-effort media path extraction from context dict."""
    for key in ("media_path", "video_path", "audio_path", "path", "input_path"):
        value = context_data.get(key)
        if value:
            return str(value)
    return None


def build_subtitles_from_transcription(transcription: Any) -> list[dict[str, Any]]:
    """Build subtitle entries from a transcription payload or string."""
    if isinstance(transcription, dict):
        segments = transcription.get("segments")
        if isinstance(segments, list) and segments:
            parsed: list[dict[str, Any]] = []
            for idx, segment in enumerate(segments, start=1):
                if not isinstance(segment, dict):
                    continue
                text = str(
                    segment.get("text")
                    or segment.get("src_text")
                    or segment.get("translation")
                    or ""
                ).strip()
                if not text:
                    continue
                start_seconds = to_float(segment.get("start_seconds"))
                end_seconds = to_float(segment.get("end_seconds"))
                if end_seconds is None or end_seconds <= (start_seconds or 0.0):
                    end_seconds = (start_seconds or 0.0) + 1.5
                start_time = segment.get("start_time") or seconds_to_srt(start_seconds or 0.0)
                end_time = segment.get("end_time") or seconds_to_srt(end_seconds)
                segment_index = segment.get("index")
                if isinstance(segment_index, str) and segment_index.isdigit():
                    segment_index = int(segment_index)
                if not isinstance(segment_index, int) or segment_index <= 0:
                    segment_index = idx
                parsed.append({
                    "index": segment_index,
                    "start_time": str(start_time),
                    "end_time": str(end_time),
                    "text": text,
                })
            if parsed:
                return parsed

        transcript_text = str(transcription.get("text") or "").strip()
        if transcript_text:
            duration = to_float(transcription.get("duration")) or 7.0
            return [{
                "index": 1,
                "start_time": "00:00:00,000",
                "end_time": seconds_to_srt(duration),
                "text": transcript_text,
            }]

    if isinstance(transcription, str):
        transcript_text = transcription.strip()
        if transcript_text:
            return [{
                "index": 1,
                "start_time": "00:00:00,000",
                "end_time": "00:00:07,000",
                "text": transcript_text,
            }]

    return []
