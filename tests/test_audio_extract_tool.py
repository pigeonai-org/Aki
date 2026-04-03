"""Tests for audio extraction tool."""

from pathlib import Path

import pytest

from aki.tools import ToolRegistry
from aki.tools.audio.extract import AudioExtractTool


@pytest.mark.asyncio
async def test_audio_extract_skips_when_input_is_audio(tmp_path):
    """Audio input should bypass ffmpeg extraction."""
    audio_file = tmp_path / "sample.mp3"
    audio_file.write_bytes(b"fake-audio")

    tool = AudioExtractTool()
    result = await tool(video_path=str(audio_file))

    assert result.success
    assert result.data["audio_path"] == str(audio_file)
    assert result.data["skipped"] is True


@pytest.mark.asyncio
async def test_audio_extract_runs_ffmpeg_for_video(monkeypatch, tmp_path):
    """Video input should invoke ffmpeg and return extracted path."""
    video_file = tmp_path / "sample.mp4"
    video_file.write_bytes(b"fake-video")

    monkeypatch.setattr("aki.tools.audio.extract.shutil.which", lambda _: "/usr/bin/ffmpeg")

    def _fake_run(command, check, capture_output, text):
        output_path = Path(command[-1])
        output_path.write_bytes(b"fake-mp3")

    monkeypatch.setattr("aki.tools.audio.extract.subprocess.run", _fake_run)

    tool = AudioExtractTool()
    result = await tool(video_path=str(video_file))

    assert result.success
    assert result.data["audio_path"].endswith(".asr.mp3")
    assert result.data["skipped"] is False


def test_audio_extract_registered():
    """Tool should be available in registry."""
    tool = ToolRegistry.get("audio_extract")
    assert tool.name == "audio_extract"
