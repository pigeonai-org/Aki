"""Audio VAD Tool

Pyannote-based VAD/diarization (default) with pydub chunk export for ASR.
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any

import requests
from pydub import AudioSegment

from aki.config import get_settings
from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.registry import ToolRegistry

PYANNOTE_MEDIA_INPUT_ENDPOINT = "https://api.pyannote.ai/v1/media/input"
PYANNOTE_DIARIZE_ENDPOINT = "https://api.pyannote.ai/v1/diarize"
PYANNOTE_JOBS_ENDPOINT = "https://api.pyannote.ai/v1/jobs"
SUPPORTED_VAD_PROVIDERS = {"pyannote_api"}


def _seconds_to_srt(seconds: float) -> str:
    """Convert seconds to SRT timestamp HH:MM:SS,mmm."""
    total_ms = max(0, int(round(float(seconds) * 1000)))
    hours = total_ms // 3600000
    total_ms %= 3600000
    minutes = total_ms // 60000
    total_ms %= 60000
    secs = total_ms // 1000
    ms = total_ms % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _ms_to_filename_time(ms: int) -> str:
    """Convert milliseconds to filename-safe HH-MM-SS-mmm."""
    total_s = ms // 1000
    rem_ms = ms % 1000
    secs = total_s % 60
    total_m = total_s // 60
    minutes = total_m % 60
    hours = total_m // 60
    return f"{hours:02d}-{minutes:02d}-{secs:02d}-{rem_ms:03d}"


def _normalize_api_key(api_key: str | None) -> str | None:
    """Normalize API key value."""
    if api_key is None:
        return None
    normalized = str(api_key).strip()
    if normalized.lower().startswith("bearer "):
        normalized = normalized[7:].strip()
    return normalized or None


def _is_url(path: str) -> bool:
    """Return whether path is an HTTP(S) or media:// URL."""
    normalized = str(path).strip().lower()
    return (
        normalized.startswith("http://")
        or normalized.startswith("https://")
        or normalized.startswith("media://")
    )


def _auth_headers_json(api_key: str) -> dict[str, str]:
    """Auth header helper for JSON requests."""
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _upload_media(api_key: str, audio_path: str) -> str:
    """Upload local file to pyannote temporary media storage and return media:// URL."""
    if _is_url(audio_path):
        return audio_path

    local_path = Path(audio_path).expanduser()
    if not local_path.exists():
        raise FileNotFoundError(f"Media file not found: {audio_path}")

    object_key = f"aki_{uuid.uuid4().hex}"
    media_url = f"media://{object_key}"

    presign_response = requests.post(
        PYANNOTE_MEDIA_INPUT_ENDPOINT,
        json={"url": media_url},
        headers=_auth_headers_json(api_key),
        timeout=30,
    )
    presign_response.raise_for_status()
    upload_url = (presign_response.json() or {}).get("url")
    if not upload_url:
        raise RuntimeError("Pyannote media/input response missing upload URL")

    with local_path.open("rb") as file_handle:
        upload_response = requests.put(
            upload_url,
            data=file_handle,
            headers={"Content-Type": "application/octet-stream"},
            timeout=120,
        )
    upload_response.raise_for_status()
    return media_url


def _create_diarization_job(
    api_key: str,
    media_url: str,
    model: str,
    webhook_url: str | None,
) -> str:
    """Create pyannote diarization job and return job id."""
    payload: dict[str, str] = {
        "url": media_url,
        "model": model,
    }
    if webhook_url:
        payload["webhook"] = webhook_url

    response = requests.post(
        PYANNOTE_DIARIZE_ENDPOINT,
        json=payload,
        headers=_auth_headers_json(api_key),
        timeout=30,
    )
    response.raise_for_status()
    data = response.json() or {}

    job_id = data.get("jobId") or data.get("id")
    if not job_id:
        raise RuntimeError(f"Pyannote diarize response missing job id: {data}")
    return str(job_id)


def _poll_diarization_result(
    api_key: str,
    job_id: str,
    poll_interval_seconds: float,
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    """Poll pyannote job until completion and return diarization segments."""
    deadline = time.time() + max(1.0, timeout_seconds)
    poll_interval = max(0.2, float(poll_interval_seconds))
    endpoint = f"{PYANNOTE_JOBS_ENDPOINT}/{job_id}"

    while True:
        response = requests.get(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )

        if response.status_code == 404:
            if time.time() >= deadline:
                raise TimeoutError(f"Pyannote job not found before timeout: {job_id}")
            time.sleep(min(2.0, poll_interval))
            continue

        if response.status_code == 429:
            if time.time() >= deadline:
                raise TimeoutError(f"Pyannote polling rate-limited until timeout: {job_id}")
            time.sleep(max(2.0, poll_interval))
            continue

        response.raise_for_status()
        payload = response.json() or {}
        status = str(payload.get("status") or "").lower()

        if status == "succeeded":
            output = payload.get("output") or {}
            diarization = output.get("diarization") or []
            if not isinstance(diarization, list):
                return []
            try:
                diarization.sort(key=lambda seg: float(seg.get("start") or 0.0))
            except Exception:
                pass
            return diarization

        if status == "failed":
            error_detail = payload.get("error") or payload
            raise RuntimeError(f"Pyannote diarization job failed: {error_detail}")

        if time.time() >= deadline:
            raise TimeoutError(f"Pyannote diarization polling timed out: {job_id}")
        time.sleep(poll_interval)


def _split_by_max_duration(
    start: float,
    end: float,
    max_chunk_seconds: float,
) -> list[tuple[float, float]]:
    """Split a segment by max duration."""
    duration = end - start
    if max_chunk_seconds <= 0 or duration <= max_chunk_seconds:
        return [(start, end)]

    chunks: list[tuple[float, float]] = []
    cursor = start
    while cursor < end:
        chunk_end = min(end, cursor + max_chunk_seconds)
        if chunk_end > cursor:
            chunks.append((cursor, chunk_end))
        cursor = chunk_end
    return chunks


def _normalize_diarization_segments(
    segments: list[dict[str, Any]],
    min_segment_seconds: float,
    overlap_tolerance: float = 0.02,
) -> list[tuple[float, float, Any]]:
    """Normalize and de-overlap diarization intervals."""
    normalized: list[tuple[float, float, Any]] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        try:
            start = float(segment.get("start") or 0.0)
            end = float(segment.get("end") or 0.0)
        except Exception:
            continue

        if end <= start:
            continue

        if end - start < min_segment_seconds:
            continue

        speaker = segment.get("speaker")
        normalized.append((start, end, speaker))

    if not normalized:
        return []

    normalized.sort(key=lambda item: item[0])
    merged: list[tuple[float, float, Any]] = []
    for start, end, speaker in normalized:
        if not merged:
            merged.append((start, end, speaker))
            continue

        prev_start, prev_end, prev_speaker = merged[-1]
        if start <= prev_end + overlap_tolerance and (
            prev_speaker == speaker or prev_speaker is None or speaker is None
        ):
            if end <= prev_end:
                continue
            merged[-1] = (
                min(prev_start, start),
                max(prev_end, end),
                prev_speaker if prev_speaker is not None else speaker,
            )
            continue

        # For speaker transitions, keep boundaries intact and only trim true overlap.
        if start < prev_end:
            start = prev_end
            if end <= start:
                continue
            if end - start < min_segment_seconds:
                continue

        merged.append((start, end, speaker))

    return merged


def _load_and_prepare_audio(
    source_path: str,
    sample_rate: int,
    channels: int,
) -> AudioSegment:
    """Load source once and normalize for in-memory chunk slicing."""
    audio = AudioSegment.from_file(source_path)
    audio = audio.set_channels(int(channels))
    audio = audio.set_frame_rate(int(sample_rate))
    return audio


@ToolRegistry.register
class AudioVADTool(BaseTool):
    """Pyannote-based VAD that exports timestamped audio chunks."""

    name = "audio_vad"
    description = "Run pyannote diarization and split media into VAD audio chunks"
    parameters = [
        ToolParameter(
            name="audio_path",
            type="string",
            description="Path or URL to source audio/video media",
        ),
        ToolParameter(
            name="output_dir",
            type="string",
            description="Optional directory for chunk files",
            required=False,
            default=None,
        ),
    ]

    async def execute(
        self,
        audio_path: str,
        output_dir: str | None = None,
        provider: str = "pyannote_api",
        model: str = "precision-2",
        api_key: str | None = None,
        webhook_url: str | None = None,
        min_segment_seconds: float = 0.6,
        max_chunk_seconds: float = 24.0,
        poll_interval_seconds: float = 1.0,
        timeout_seconds: float = 600.0,
        sample_rate: int = 16000,
        channels: int = 1,
        bitrate: str = "48k",
        **kwargs: Any,
    ) -> ToolResult:
        """Run pyannote diarization and export chunked audio from resulting segments."""
        del kwargs

        provider_name = str(provider or "pyannote_api").strip().lower()
        if provider_name not in SUPPORTED_VAD_PROVIDERS:
            allowed = ", ".join(sorted(SUPPORTED_VAD_PROVIDERS))
            return ToolResult.fail(f"Unsupported VAD provider: {provider_name}. Allowed: {allowed}")

        settings = get_settings()
        resolved_api_key = _normalize_api_key(
            api_key
            or settings.pyannote_api_key
            or os.environ.get("AKI_PYANNOTE_API_KEY")
            or os.environ.get("PYANNOTE_API_KEY")
        )
        if not resolved_api_key:
            return ToolResult.fail(
                "Pyannote VAD authentication failed. Set AKI_PYANNOTE_API_KEY "
                "(or PYANNOTE_API_KEY)."
            )

        source_path = str(Path(audio_path).expanduser()) if not _is_url(audio_path) else audio_path
        if not _is_url(source_path) and not Path(source_path).exists():
            return ToolResult.fail(f"Media file not found: {audio_path}")

        if _is_url(source_path):
            return ToolResult.fail(
                "Pyannote VAD chunk export requires a local audio_path. "
                "Provide a local file path for audio chunk generation."
            )

        try:
            media_url = _upload_media(resolved_api_key, source_path)
            job_id = _create_diarization_job(
                api_key=resolved_api_key,
                media_url=media_url,
                model=str(model or "precision-2"),
                webhook_url=webhook_url,
            )
            diarization_segments = _poll_diarization_result(
                api_key=resolved_api_key,
                job_id=job_id,
                poll_interval_seconds=float(poll_interval_seconds),
                timeout_seconds=float(timeout_seconds),
            )
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            body = exc.response.text if exc.response is not None else str(exc)
            return ToolResult.fail(f"Pyannote API request failed ({status}): {body}")
        except Exception as exc:
            return ToolResult.fail(f"Pyannote VAD failed: {exc}")

        min_duration = max(0.0, float(min_segment_seconds))
        max_duration = max(0.0, float(max_chunk_seconds))

        if output_dir:
            target_dir = Path(output_dir).expanduser()
        else:
            source_local = Path(source_path).expanduser()
            target_dir = source_local.parent / f"{source_local.stem}.vad_chunks"
        target_dir.mkdir(parents=True, exist_ok=True)

        try:
            prepared_audio = _load_and_prepare_audio(
                source_path=source_path,
                sample_rate=int(sample_rate),
                channels=int(channels),
            )
        except Exception as exc:
            return ToolResult.fail(f"Pyannote chunk loading failed: {exc}")

        chunks: list[dict[str, Any]] = []
        normalized_segments = _normalize_diarization_segments(
            diarization_segments,
            min_segment_seconds=min_duration,
        )
        for start, end, speaker in normalized_segments:
            split_ranges = _split_by_max_duration(start, end, max_duration)
            for split_start, split_end in split_ranges:
                split_start_ms = int(round(split_start * 1000))
                split_end_ms = int(round(split_end * 1000))
                filename = (
                    f"segment_{_ms_to_filename_time(split_start_ms)}_"
                    f"{_ms_to_filename_time(split_end_ms)}.mp3"
                )
                chunk_path = target_dir / filename

                try:
                    clip = prepared_audio[split_start_ms:split_end_ms]
                    clip.export(str(chunk_path), format="mp3", bitrate=str(bitrate))
                except Exception as exc:
                    return ToolResult.fail(f"Pyannote chunk export failed: {exc}")

                chunks.append(
                    {
                        "index": len(chunks) + 1,
                        "audio_path": str(chunk_path),
                        "start_seconds": round(split_start, 3),
                        "end_seconds": round(split_end, 3),
                        "duration_seconds": round(
                            max(0.0, split_end - split_start),
                            3,
                        ),
                        "start_time": _seconds_to_srt(split_start),
                        "end_time": _seconds_to_srt(split_end),
                        "speaker": speaker,
                    }
                )

        if not chunks:
            return ToolResult.fail(
                "Pyannote VAD completed but produced no usable segments. "
                "Try lowering min_segment_seconds or checking input audio quality."
            )

        return ToolResult.ok(
            data={
                "audio_path": source_path,
                "chunk_dir": str(target_dir),
                "chunks": chunks,
                "count": len(chunks),
                "provider": provider_name,
                "model": str(model or "precision-2"),
                "job_id": job_id,
            },
            provider=provider_name,
            model=str(model or "precision-2"),
        )
