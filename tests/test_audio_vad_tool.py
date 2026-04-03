"""Tests for pyannote-based audio_vad tool."""

from pathlib import Path

import pytest
import requests

from aki.config import reset_settings
from aki.tools.audio.vad import (
    PYANNOTE_DIARIZE_ENDPOINT,
    PYANNOTE_JOBS_ENDPOINT,
    PYANNOTE_MEDIA_INPUT_ENDPOINT,
    AudioVADTool,
)


class _FakeResponse:
    """Minimal requests.Response stub."""

    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self):
        return self._payload


class _FakeClip:
    """Fake pydub clip for export assertions."""

    def __init__(self, duration_ms: int, exports: list[dict]):
        self._duration_ms = duration_ms
        self._exports = exports

    def export(self, output_path: str, format: str = "mp3", bitrate: str = "48k"):
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"chunk")
        self._exports.append(
            {
                "path": str(path),
                "format": format,
                "bitrate": bitrate,
                "duration_ms": self._duration_ms,
            }
        )
        return path


class _FakeAudioTrack:
    """Fake pydub AudioSegment object."""

    def __init__(self, exports: list[dict], duration_ms: int = 60000):
        self._exports = exports
        self._duration_ms = duration_ms

    def set_channels(self, channels: int):
        del channels
        return self

    def set_frame_rate(self, sample_rate: int):
        del sample_rate
        return self

    def __getitem__(self, item):
        start_ms = int(getattr(item, "start", 0) or 0)
        end_ms = int(getattr(item, "stop", self._duration_ms) or self._duration_ms)
        duration_ms = max(0, end_ms - start_ms)
        return _FakeClip(duration_ms=duration_ms, exports=self._exports)


def _mock_audio_segment(monkeypatch, exports: list[dict]) -> None:
    """Patch AudioSegment.from_file to return a fake reusable track."""

    class _FakeAudioSegment:
        @staticmethod
        def from_file(path):
            del path
            return _FakeAudioTrack(exports=exports)

    monkeypatch.setattr("aki.tools.audio.vad.AudioSegment", _FakeAudioSegment)


@pytest.mark.asyncio
async def test_audio_vad_pyannote_api_success(monkeypatch, tmp_path):
    """audio_vad should run pyannote API flow and export diarization chunks."""
    source = tmp_path / "demo.mp3"
    source.write_bytes(b"fake-audio")

    def _fake_post(url, json=None, headers=None, timeout=None):
        del headers, timeout
        if url == PYANNOTE_MEDIA_INPUT_ENDPOINT:
            assert json["url"].startswith("media://")
            return _FakeResponse(payload={"url": "https://upload.example.com/signed"})
        if url == PYANNOTE_DIARIZE_ENDPOINT:
            assert json["model"] == "precision-2"
            return _FakeResponse(payload={"jobId": "job-123"})
        raise AssertionError(f"unexpected POST {url}")

    def _fake_put(url, data=None, headers=None, timeout=None):
        del data, headers, timeout
        assert url == "https://upload.example.com/signed"
        return _FakeResponse()

    def _fake_get(url, headers=None, timeout=None):
        del headers, timeout
        assert url == f"{PYANNOTE_JOBS_ENDPOINT}/job-123"
        return _FakeResponse(
            payload={
                "status": "succeeded",
                "output": {
                    "diarization": [
                        {"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"},
                        {"start": 2.0, "end": 5.5, "speaker": "SPEAKER_01"},
                    ]
                },
            }
        )

    exports: list[dict] = []
    _mock_audio_segment(monkeypatch, exports)

    monkeypatch.setattr("aki.tools.audio.vad.requests.post", _fake_post)
    monkeypatch.setattr("aki.tools.audio.vad.requests.put", _fake_put)
    monkeypatch.setattr("aki.tools.audio.vad.requests.get", _fake_get)

    tool = AudioVADTool()
    result = await tool(
        audio_path=str(source),
        output_dir=str(tmp_path / "chunks"),
        api_key="pyannote-key",
    )

    assert result.success
    assert result.data["provider"] == "pyannote_api"
    assert result.data["model"] == "precision-2"
    assert result.data["job_id"] == "job-123"
    assert result.data["count"] == 2
    assert result.data["chunks"][0]["speaker"] == "SPEAKER_00"
    assert result.data["chunks"][1]["start_seconds"] == 2.0
    assert result.data["chunks"][1]["end_seconds"] == 5.5
    assert len(exports) == 2
    assert all(item["format"] == "mp3" for item in exports)


@pytest.mark.asyncio
async def test_audio_vad_requires_pyannote_api_key(monkeypatch, tmp_path):
    """audio_vad should fail when pyannote API key is not configured."""
    source = tmp_path / "demo.mp3"
    source.write_bytes(b"fake-audio")

    monkeypatch.delenv("AKI_PYANNOTE_API_KEY", raising=False)
    monkeypatch.delenv("PYANNOTE_API_KEY", raising=False)
    reset_settings()
    monkeypatch.setattr(
        "aki.tools.audio.vad.get_settings",
        lambda: type("_Settings", (), {"pyannote_api_key": None})(),
    )

    tool = AudioVADTool()
    result = await tool(audio_path=str(source))

    assert not result.success
    assert "AKI_PYANNOTE_API_KEY" in (result.error or "")


@pytest.mark.asyncio
async def test_audio_vad_uses_pyannote_as_default_provider(monkeypatch, tmp_path):
    """audio_vad should default to pyannote_api provider."""
    source = tmp_path / "demo.mp3"
    source.write_bytes(b"fake-audio")

    call_log = {"post": 0}

    def _fake_post(url, json=None, headers=None, timeout=None):
        del json, headers, timeout
        call_log["post"] += 1
        if url == PYANNOTE_MEDIA_INPUT_ENDPOINT:
            return _FakeResponse(payload={"url": "https://upload.example.com/signed"})
        if url == PYANNOTE_DIARIZE_ENDPOINT:
            return _FakeResponse(payload={"jobId": "job-123"})
        raise AssertionError(f"unexpected POST {url}")

    monkeypatch.setattr("aki.tools.audio.vad.requests.post", _fake_post)
    monkeypatch.setattr("aki.tools.audio.vad.requests.put", lambda *a, **k: _FakeResponse())
    monkeypatch.setattr(
        "aki.tools.audio.vad.requests.get",
        lambda *a, **k: _FakeResponse(
            payload={
                "status": "succeeded",
                "output": {
                    "diarization": [{"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"}]
                },
            }
        ),
    )

    exports: list[dict] = []
    _mock_audio_segment(monkeypatch, exports)

    tool = AudioVADTool()
    result = await tool(audio_path=str(source), api_key="pyannote-key")

    assert result.success
    assert call_log["post"] >= 2
    assert len(exports) == 1


@pytest.mark.asyncio
async def test_audio_vad_splits_long_segments(monkeypatch, tmp_path):
    """Long pyannote segments should be split by max_chunk_seconds."""
    source = tmp_path / "demo.mp3"
    source.write_bytes(b"fake-audio")

    monkeypatch.setattr(
        "aki.tools.audio.vad.requests.post",
        lambda url, **kwargs: (
            _FakeResponse(payload={"url": "https://upload.example.com/signed"})
            if url == PYANNOTE_MEDIA_INPUT_ENDPOINT
            else _FakeResponse(payload={"jobId": "job-123"})
        ),
    )
    monkeypatch.setattr("aki.tools.audio.vad.requests.put", lambda *a, **k: _FakeResponse())
    monkeypatch.setattr(
        "aki.tools.audio.vad.requests.get",
        lambda *a, **k: _FakeResponse(
            payload={
                "status": "succeeded",
                "output": {
                    "diarization": [{"start": 0.0, "end": 12.0, "speaker": "SPEAKER_00"}]
                },
            }
        ),
    )

    exports: list[dict] = []
    _mock_audio_segment(monkeypatch, exports)

    tool = AudioVADTool()
    result = await tool(
        audio_path=str(source),
        output_dir=str(tmp_path / "chunks"),
        api_key="pyannote-key",
        max_chunk_seconds=5.0,
    )

    assert result.success
    assert result.data["count"] == 3
    assert result.data["chunks"][0]["start_seconds"] == 0.0
    assert result.data["chunks"][0]["end_seconds"] == 5.0
    assert result.data["chunks"][1]["start_seconds"] == 5.0
    assert result.data["chunks"][1]["end_seconds"] == 10.0
    assert result.data["chunks"][2]["start_seconds"] == 10.0
    assert result.data["chunks"][2]["end_seconds"] == 12.0
    assert len(exports) == 3


@pytest.mark.asyncio
async def test_audio_vad_drops_zero_length_segments_after_overlap_trim(monkeypatch, tmp_path):
    """Overlap-trimmed speaker transitions must not emit zero-length chunks."""
    source = tmp_path / "demo.mp3"
    source.write_bytes(b"fake-audio")

    monkeypatch.setattr(
        "aki.tools.audio.vad.requests.post",
        lambda url, **kwargs: (
            _FakeResponse(payload={"url": "https://upload.example.com/signed"})
            if url == PYANNOTE_MEDIA_INPUT_ENDPOINT
            else _FakeResponse(payload={"jobId": "job-123"})
        ),
    )
    monkeypatch.setattr("aki.tools.audio.vad.requests.put", lambda *a, **k: _FakeResponse())
    monkeypatch.setattr(
        "aki.tools.audio.vad.requests.get",
        lambda *a, **k: _FakeResponse(
            payload={
                "status": "succeeded",
                "output": {
                    "diarization": [
                        {"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"},
                        {"start": 1.8, "end": 2.0, "speaker": "SPEAKER_01"},
                        {"start": 2.0, "end": 3.0, "speaker": "SPEAKER_01"},
                    ]
                },
            }
        ),
    )

    exports: list[dict] = []
    _mock_audio_segment(monkeypatch, exports)

    tool = AudioVADTool()
    result = await tool(
        audio_path=str(source),
        output_dir=str(tmp_path / "chunks"),
        api_key="pyannote-key",
        min_segment_seconds=0,
    )

    assert result.success
    assert result.data["count"] == 2
    assert all(chunk["duration_seconds"] > 0 for chunk in result.data["chunks"])
    assert all(item["duration_ms"] > 0 for item in exports)
