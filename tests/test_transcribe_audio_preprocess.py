"""Tests for transcribe input preprocessing."""

from pathlib import Path

import pytest

import aki.tools.audio.transcribe as transcribe_module
from aki.models import ModelConfig
from aki.tools.audio.transcribe import TranscribeTool


def test_prepare_audio_input_extracts_video_for_qwen(monkeypatch, tmp_path):
    """Local video input should be converted to compressed audio for qwen."""
    video_file = tmp_path / "sample.mp4"
    video_file.write_bytes(b"not-a-real-video")

    monkeypatch.setattr(transcribe_module.shutil, "which", lambda _: "/opt/homebrew/bin/ffmpeg")

    def _fake_ffmpeg_run(command, check, capture_output, text):
        output = Path(command[-1])
        output.write_bytes(b"fake-mp3-data")

    monkeypatch.setattr(transcribe_module.subprocess, "run", _fake_ffmpeg_run)

    prepared_path, temp_path = transcribe_module._prepare_audio_input(str(video_file), "qwen")

    assert prepared_path.endswith(".mp3")
    assert temp_path == prepared_path
    assert Path(prepared_path).exists()

    Path(prepared_path).unlink(missing_ok=True)


def test_prepare_audio_input_skips_extraction_for_non_qwen(tmp_path):
    """Non-qwen providers should keep the original media path."""
    video_file = tmp_path / "sample.mp4"
    video_file.write_bytes(b"not-a-real-video")

    prepared_path, temp_path = transcribe_module._prepare_audio_input(str(video_file), "openai")

    assert prepared_path == str(video_file)
    assert temp_path is None


def test_prepare_audio_input_skips_when_ffmpeg_missing(monkeypatch, tmp_path):
    """qwen provider should keep original file if ffmpeg is unavailable."""
    video_file = tmp_path / "sample.mp4"
    video_file.write_bytes(b"not-a-real-video")

    monkeypatch.setattr(transcribe_module.shutil, "which", lambda _: None)

    prepared_path, temp_path = transcribe_module._prepare_audio_input(str(video_file), "qwen")

    assert prepared_path == str(video_file)
    assert temp_path is None


def test_parse_provider_spec_accepts_default_alias(monkeypatch):
    """'default' provider should resolve to the configured default audio provider."""
    class _DefaultConfig:
        provider = "openai"
        model_name = "whisper-1"

    monkeypatch.setattr(
        transcribe_module,
        "_get_default_audio_config",
        lambda: _DefaultConfig(),
    )

    provider_name, provider_model = transcribe_module._parse_provider_spec("default")

    assert provider_name == "openai"
    assert provider_model is None


def test_normalize_language_variants_to_iso1():
    """Language normalization should map common alias formats to ISO-639-1 codes."""
    assert transcribe_module._normalize_language_code("zh-CN") == "zh"
    assert transcribe_module._normalize_language_code("Chinese") == "zh"
    assert transcribe_module._normalize_language_code("EN") == "en"
    assert transcribe_module._normalize_language_code("cmn") == "zh"
    assert transcribe_module._normalize_language_code("eng-US") == "en"


@pytest.mark.asyncio
async def test_transcribe_tool_uses_normalized_language_for_model_call(monkeypatch):
    """Transcribe should pass normalized language to model transcribe calls."""
    recorded = {}

    class _MockModel:
        async def transcribe(self, **kwargs):
            recorded["language"] = kwargs.get("language")

            class _Response:
                model = "whisper-1"
                metadata = {"segments": [], "language": None, "duration": None}

            response = _Response()
            response.content = "ok"
            return response

    monkeypatch.setattr(
        transcribe_module,
        "_prepare_audio_input",
        lambda audio_path, provider: ("prepared.mp3", None),
    )

    tool = TranscribeTool(
        audio_model=_MockModel(),
        model_config=ModelConfig(provider="openai", model_name="whisper-1"),
    )
    result = await tool(
        audio_path="x.mp3",
        language="Chinese",
        provider="openai",
        model="whisper-1",
    )

    assert result.success
    assert recorded["language"] == "zh"


@pytest.mark.asyncio
async def test_transcribe_tool_defaults_to_default_audio_provider(monkeypatch, tmp_path):
    """When provider is omitted, transcription should follow configured default_audio."""
    prepared_providers: list[str] = []

    class _MockModel:
        async def transcribe(self, **kwargs):
            class _Response:
                model = "whisper-1"
                metadata = {"segments": [], "language": None, "duration": None}

            response = _Response()
            response.content = "ok"
            return response

    monkeypatch.setattr(
        transcribe_module,
        "_get_default_audio_config",
        lambda provider=None, model=None: ModelConfig(provider="openai", model_name="whisper-1"),
    )

    def _fake_prepare_audio_input(audio_path: str, provider: str):
        prepared_providers.append(provider)
        prepared_file = tmp_path / "prepared.mp3"
        prepared_file.write_bytes(b"audio")
        return str(prepared_file), None

    monkeypatch.setattr(transcribe_module, "_prepare_audio_input", _fake_prepare_audio_input)
    monkeypatch.setattr(transcribe_module.Path, "unlink", lambda self, missing_ok=True: None)

    tool = TranscribeTool(audio_model=_MockModel())
    result = await tool(
        audio_path="x.mp3",
        language="en",
    )

    assert result.success
    assert prepared_providers == ["openai"]


@pytest.mark.asyncio
async def test_transcribe_tool_chunks_qwen_audio_when_too_long(monkeypatch):
    """Qwen transcription should fallback to chunked audio when provider says too long."""

    class _ChunkingAudioModel:
        async def transcribe(self, **kwargs):
            audio = kwargs["audio"]
            if audio == "prepared.mp3":
                raise RuntimeError("DashScope request failed (400): The audio is too long")

            class _Response:
                model = "qwen3-asr-flash"
                metadata = {"segments": [], "language": "en", "duration": None}

            response = _Response()
            response.content = f"text-for-{audio}"
            return response

    monkeypatch.setattr(
        transcribe_module,
        "_prepare_audio_input",
        lambda audio_path, provider: ("prepared.mp3", "prepared.mp3"),
    )
    monkeypatch.setattr(
        transcribe_module,
        "_split_audio_into_chunks",
        lambda audio_path, chunk_seconds=480: (["chunk1.mp3", "chunk2.mp3"], "chunk-dir"),
    )

    cleaned_dirs = []

    def _record_cleanup(chunk_dir):
        cleaned_dirs.append(chunk_dir)

    monkeypatch.setattr(transcribe_module, "_cleanup_chunk_dir", _record_cleanup)
    monkeypatch.setattr(
        transcribe_module.Path,
        "unlink",
        lambda self, missing_ok=True: None,
    )

    tool = TranscribeTool(
        audio_model=_ChunkingAudioModel(),
        model_config=ModelConfig(provider="qwen", model_name="qwen3-asr-flash"),
    )
    result = await tool(
        audio_path="XIAOMI.mp4",
        language="en",
        provider="qwen",
        model="qwen3-asr-flash",
    )

    assert result.success
    assert "text-for-chunk1.mp3" in result.data["text"]
    assert "text-for-chunk2.mp3" in result.data["text"]
    assert cleaned_dirs == ["chunk-dir"]


@pytest.mark.asyncio
async def test_transcribe_uses_chunk_manifest_and_offsets_segments(monkeypatch):
    """Provided chunk manifests should be transcribed with preserved timing offsets."""

    class _ChunkModel:
        async def transcribe(self, **kwargs):
            audio = kwargs["audio"]

            class _Response:
                model = "qwen3-asr-flash"
                usage = {}
                metadata = {
                    "segments": [
                        {"start": 0.0, "end": 1.2, "text": f"{audio}-part"},
                    ],
                    "language": "en",
                    "duration": 1.2,
                }

            response = _Response()
            response.content = f"text-for-{audio}"
            return response

    monkeypatch.setattr(
        transcribe_module,
        "_prepare_audio_input",
        lambda audio_path, provider: ("prepared.mp3", "prepared.mp3"),
    )
    monkeypatch.setattr(
        transcribe_module.Path,
        "unlink",
        lambda self, missing_ok=True: None,
    )

    tool = TranscribeTool(
        audio_model=_ChunkModel(),
        model_config=ModelConfig(provider="qwen", model_name="qwen3-asr-flash"),
    )
    result = await tool(
        audio_path="XIAOMI.mp4",
        language="en",
        provider="qwen",
        chunks=[
            {"index": 1, "audio_path": "chunk1.mp3", "start_seconds": 0.0, "end_seconds": 2.0},
            {"index": 2, "audio_path": "chunk2.mp3", "start_seconds": 2.0, "end_seconds": 4.0},
        ],
    )

    assert result.success
    assert len(result.data["chunked_audio"]) == 2
    assert len(result.data["segments"]) == 2
    assert result.data["segments"][0]["start_time"] == "00:00:00,000"
    assert result.data["segments"][0]["end_time"] == "00:00:01,200"
    assert result.data["segments"][1]["start_time"] == "00:00:02,000"
    assert result.data["segments"][1]["end_time"] == "00:00:03,200"
