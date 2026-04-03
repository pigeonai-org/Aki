"""Transcribe Tool

Speech recognition using configurable ASR providers.
Pure executor - no decision making.
"""

from __future__ import annotations

import shutil
import subprocess
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from aki.config import get_settings
from aki.models import AudioModelInterface, ModelConfig, ModelRegistry, ModelResponse, ModelType
from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.registry import ToolRegistry

SUPPORTED_ASR_PROVIDERS = {"qwen", "openai", "google"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".flv"}
QWEN_AUDIO_MAX_CHUNK_SECONDS = 8
_PROVIDER_ALIASES = {
    "default_provider": "default",
    "provider_default": "default",
    "auto": "default",
    "default": "default",
}
_MODEL_PLACEHOLDERS = {
    "default_model",
    "base_model",
    "model",
    "default",
}
_MODEL_FALLBACK_BY_PROVIDER = {
    "qwen": "qwen3-asr-flash",
    "openai": "whisper-1",
    "google": "gemini-2.0-flash",
}
_ISO3_TO_ISO1 = {
    "eng": "en",
    "cmn": "zh",
    "zho": "zh",
    "jpn": "ja",
    "kor": "ko",
    "fra": "fr",
    "deu": "de",
    "spa": "es",
    "por": "pt",
    "rus": "ru",
    "ara": "ar",
    "hin": "hi",
}
_LANGUAGE_ALIASES = {
    "zh-cn": "zh",
    "zh_cn": "zh",
    "zh-hans": "zh",
    "zh-hant": "zh",
    "zh-hk": "zh",
    "zh-tw": "zh",
    "chinese": "zh",
    "mandarin": "zh",
}


@dataclass
class _ChunkSpec:
    index: int
    audio_path: str
    start_seconds: float
    end_seconds: float


def _get_default_audio_config(
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> ModelConfig:
    """Get audio model config with provider/model overrides from settings."""
    settings = get_settings()
    default_config = ModelConfig.from_string(settings.default_audio)
    resolved_provider = (provider or default_config.provider).strip().lower()

    if model:
        resolved_model = model.strip()
    elif resolved_provider == default_config.provider:
        resolved_model = default_config.model_name
    else:
        resolved_model = {
            "qwen": "qwen3-asr-flash",
            "openai": "whisper-1",
            "google": "gemini-2.0-flash",
        }.get(resolved_provider, default_config.model_name)

    config = ModelConfig(provider=resolved_provider, model_name=resolved_model)

    if config.provider == "openai":
        config.api_key = settings.openai_api_key
        if settings.openai_base_url:
            config.base_url = settings.openai_base_url
    elif config.provider == "google":
        config.api_key = settings.google_api_key
    elif config.provider == "qwen":
        config.api_key = settings.dashscope_api_key
    else:
        raise ValueError(f"Unsupported ASR provider: {config.provider}")
    return config


def _parse_provider_spec(provider: Optional[str]) -> tuple[str, Optional[str]]:
    """Parse provider or provider:model syntax."""
    raw_provider = (provider or "default").strip().lower()
    if ":" in raw_provider:
        provider_name, provider_model = raw_provider.split(":", 1)
        provider_name = provider_name.strip()
        provider_model = provider_model.strip() or None
    else:
        provider_name = raw_provider
        provider_model = None

    provider_name = _PROVIDER_ALIASES.get(provider_name, provider_name)
    if provider_name == "default":
        provider_name = _get_default_audio_config().provider

    if provider_name not in SUPPORTED_ASR_PROVIDERS:
        allowed = ", ".join(sorted(SUPPORTED_ASR_PROVIDERS))
        raise ValueError(f"Unsupported provider: {provider_name}. Allowed: {allowed}")

    return provider_name, provider_model


def _normalize_model_alias(model: Optional[str]) -> Optional[str]:
    """Normalize legacy placeholders and empty model values."""
    if model is None:
        return None

    normalized = model.strip()
    if not normalized:
        return None

    if ":" in normalized:
        provider_name, maybe_name = normalized.split(":", 1)
        provider_name = provider_name.strip()
        provider_name = _PROVIDER_ALIASES.get(provider_name, provider_name)
        model_name = maybe_name.strip()
        if not model_name or model_name.lower() in _MODEL_PLACEHOLDERS:
            return f"{provider_name}:"
        return normalized

    if normalized.lower() in _MODEL_PLACEHOLDERS:
        return None
    return model.strip()


def _normalize_language_code(language: Optional[str]) -> Optional[str]:
    """Normalize language hints to provider-safe values."""
    if language is None:
        return None

    normalized = str(language).strip().lower().replace("_", "-")
    normalized = " ".join(normalized.split())
    if not normalized:
        return None

    if normalized in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[normalized]

    if normalized in _ISO3_TO_ISO1:
        return _ISO3_TO_ISO1[normalized]

    if "-" in normalized:
        normalized_prefix = normalized.split("-", 1)[0].strip()
        if normalized_prefix in _ISO3_TO_ISO1:
            return _ISO3_TO_ISO1[normalized_prefix]
        if len(normalized_prefix) == 2:
            return normalized_prefix

    return normalized


def _normalize_model_override(model: Optional[str], provider: str) -> Optional[str]:
    """Normalize optional model override and support provider:model compact syntax."""
    if model is None:
        return None

    normalized_model = _normalize_model_alias(model)
    if normalized_model is None:
        return None
    if not normalized_model:
        return None

    if ":" not in normalized_model:
        return normalized_model

    model_provider, model_name = normalized_model.split(":", 1)
    model_provider = model_provider.strip().lower()
    if model_provider == "default":
        model_provider = provider
    model_name = model_name.strip()
    if not model_name or model_name.lower() in _MODEL_PLACEHOLDERS:
        return None

    if model_provider not in SUPPORTED_ASR_PROVIDERS:
        raise ValueError(f"Unsupported model provider in model override: {model_provider}")

    if not model_name:
        raise ValueError(f"Invalid model format: {model}. Expected 'provider:model_name'.")

    if model_provider != provider:
        raise ValueError(
            f"Provider/model mismatch: provider={provider}, model={model}. "
            "Use the same provider in both fields."
        )

    return model_name


_SEGMENT_FILE_RE = re.compile(
    r"^segment_(\d{2}-\d{2}-\d{2}-\d{3})_(\d{2}-\d{2}-\d{2}-\d{3})\.mp3$"
)


def _segment_filename_to_seconds(token: str) -> Optional[float]:
    """Parse HH-MM-SS-mmm filename timestamp token."""
    parts = token.split("-")
    if len(parts) != 4:
        return None
    try:
        hours, minutes, seconds, millis = (int(value) for value in parts)
    except ValueError:
        return None
    if not (0 <= minutes < 60 and 0 <= seconds < 60 and 0 <= millis < 1000):
        return None
    return hours * 3600 + minutes * 60 + seconds + millis / 1000.0


def _infer_chunk_specs_from_segment_filenames(audio_path: str) -> list[_ChunkSpec]:
    """Infer a VAD chunk manifest from neighboring segment_*.mp3 files."""
    source_path = Path(audio_path).expanduser()
    if not source_path.exists():
        return []

    candidates: list[tuple[float, _ChunkSpec]] = []
    for chunk_path in source_path.parent.glob("segment_*.mp3"):
        match = _SEGMENT_FILE_RE.match(chunk_path.name)
        if not match:
            continue

        start_seconds = _segment_filename_to_seconds(match.group(1))
        end_seconds = _segment_filename_to_seconds(match.group(2))
        if start_seconds is None or end_seconds is None:
            continue
        if end_seconds <= start_seconds:
            continue

        parsed_path = str(chunk_path)
        candidates.append(
            (
                start_seconds,
                _ChunkSpec(
                    index=0,
                    audio_path=parsed_path,
                    start_seconds=start_seconds,
                    end_seconds=end_seconds,
                ),
            )
        )

    if not candidates:
        return []

    # Use inferred manifest only when the active audio path is one of these chunks.
    if str(source_path) not in {spec.audio_path for _, spec in candidates}:
        return []

    candidates.sort(key=lambda item: item[0])
    chunk_specs: list[_ChunkSpec] = []
    for idx, (_, spec) in enumerate(candidates, start=1):
        duration = _probe_audio_duration_seconds(spec.audio_path)
        if duration and duration > 0:
            adjusted_end = spec.start_seconds + duration
        else:
            adjusted_end = spec.end_seconds

        if adjusted_end <= spec.start_seconds:
            continue
        chunk_specs.append(
            _ChunkSpec(
                index=idx,
                audio_path=spec.audio_path,
                start_seconds=round(float(spec.start_seconds), 3),
                end_seconds=round(float(adjusted_end), 3),
            )
        )

    return chunk_specs


def _prepare_audio_input(audio_path: str, provider: str) -> tuple[str, Optional[str]]:
    """Prepare an audio input path for ASR providers."""
    resolved_path = Path(audio_path).expanduser()
    if not resolved_path.exists():
        return audio_path, None

    if provider != "qwen" or resolved_path.suffix.lower() not in VIDEO_EXTENSIONS:
        return str(resolved_path), None

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        return str(resolved_path), None

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        output_audio = Path(tmp.name)

    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(resolved_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        "48k",
        str(output_audio),
    ]

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise RuntimeError(f"ffmpeg audio extraction failed: {stderr or str(exc)}") from exc

    return str(output_audio), str(output_audio)


def _probe_audio_duration_seconds(audio_path: str) -> Optional[float]:
    """Probe media duration with ffprobe."""
    ffprobe_path = shutil.which("ffprobe")
    if not ffprobe_path:
        return None

    command = [
        ffprobe_path,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        duration = float((completed.stdout or "").strip())
        return duration if duration > 0 else None
    except Exception:
        return None


def _split_audio_into_chunks(
    audio_path: str,
    chunk_seconds: int = QWEN_AUDIO_MAX_CHUNK_SECONDS,
) -> tuple[list[str], Optional[str]]:
    """Split local media into chunked audio files for long ASR inputs."""
    resolved_path = Path(audio_path).expanduser()
    if not resolved_path.exists():
        return [audio_path], None

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        return [str(resolved_path)], None

    chunk_dir = Path(tempfile.mkdtemp(prefix="aki_asr_chunks_"))
    output_pattern = str(chunk_dir / "chunk_%04d.mp3")

    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(resolved_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        "48k",
        "-f",
        "segment",
        "-segment_time",
        str(chunk_seconds),
        "-reset_timestamps",
        "1",
        output_pattern,
    ]

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise RuntimeError(f"ffmpeg chunking failed: {stderr or str(exc)}") from exc

    chunk_files = sorted(chunk_dir.glob("chunk_*.mp3"))
    if not chunk_files:
        return [str(resolved_path)], str(chunk_dir)

    return [str(path) for path in chunk_files], str(chunk_dir)


def _cleanup_chunk_dir(chunk_dir: Optional[str]) -> None:
    """Best-effort cleanup for temporary chunk directory."""
    if not chunk_dir:
        return

    chunk_path = Path(chunk_dir)
    try:
        for file_path in chunk_path.glob("*"):
            file_path.unlink(missing_ok=True)
        chunk_path.rmdir()
    except Exception:
        pass


def _is_qwen_audio_too_long_error(exc: Exception) -> bool:
    """Detect DashScope long-audio errors for fallback chunking."""
    lower_error = str(exc).lower()
    markers = (
        "audio is too long",
        "invalidparameter",
        "file size is too large",
    )
    return any(marker in lower_error for marker in markers)


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


def _to_seconds(value: Any) -> Optional[float]:
    """Convert numeric or SRT time to seconds."""
    if value is None:
        return None

    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric if numeric >= 0 else 0.0

    text = str(value).strip()
    if not text:
        return None

    if ":" not in text:
        try:
            numeric = float(text)
            return numeric if numeric >= 0 else 0.0
        except ValueError:
            return None

    normalized = text.replace(".", ",")
    parts = normalized.split(":")
    if len(parts) != 3:
        return None

    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        sec_part = parts[2]
        if "," in sec_part:
            secs_str, ms_str = sec_part.split(",", 1)
            secs = int(secs_str)
            millis = int(ms_str[:3].ljust(3, "0"))
        else:
            secs = int(sec_part)
            millis = 0
        return max(0.0, hours * 3600 + minutes * 60 + secs + millis / 1000.0)
    except Exception:
        return None


def _build_chunk_specs_from_paths(chunk_paths: list[str]) -> list[_ChunkSpec]:
    """Build sequential chunk specs from file paths and probe durations."""
    specs: list[_ChunkSpec] = []
    cursor = 0.0
    for idx, chunk_path in enumerate(chunk_paths, start=1):
        duration = _probe_audio_duration_seconds(chunk_path) or 0.0
        end_seconds = cursor + max(0.0, duration)
        specs.append(
            _ChunkSpec(
                index=idx,
                audio_path=chunk_path,
                start_seconds=cursor,
                end_seconds=end_seconds,
            )
        )
        cursor = end_seconds
    return specs


def _normalize_chunk_inputs(chunks: list[dict[str, Any]]) -> list[_ChunkSpec]:
    """Normalize incoming chunk manifest to internal chunk specs."""
    normalized: list[_ChunkSpec] = []
    cursor = 0.0

    for idx, item in enumerate(chunks, start=1):
        if not isinstance(item, dict):
            continue

        chunk_path = str(item.get("audio_path") or item.get("path") or "").strip()
        if not chunk_path:
            continue

        start_seconds = _to_seconds(item.get("start_seconds"))
        if start_seconds is None:
            start_seconds = _to_seconds(item.get("start_time"))
        if start_seconds is None:
            start_seconds = cursor

        end_seconds = _to_seconds(item.get("end_seconds"))
        if end_seconds is None:
            end_seconds = _to_seconds(item.get("end_time"))

        if end_seconds is None or end_seconds <= start_seconds:
            duration = _probe_audio_duration_seconds(chunk_path)
            if duration and duration > 0:
                end_seconds = start_seconds + duration
            else:
                end_seconds = start_seconds

        normalized.append(
            _ChunkSpec(
                index=int(item.get("index") or idx),
                audio_path=chunk_path,
                start_seconds=max(0.0, float(start_seconds)),
                end_seconds=max(float(start_seconds), float(end_seconds)),
            )
        )
        cursor = normalized[-1].end_seconds

    normalized.sort(key=lambda spec: (spec.start_seconds, spec.index))
    if not normalized:
        return []

    deduplicated: list[_ChunkSpec] = []
    seen: set[tuple[str, float, float]] = set()
    for spec in normalized:
        if spec.end_seconds <= spec.start_seconds:
            continue

        key = (
            spec.audio_path,
            round(spec.start_seconds, 3),
            round(spec.end_seconds, 3),
        )
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(spec)

    return deduplicated


def _segment_text(segment: dict[str, Any]) -> str:
    """Extract text content from segment-like dict."""
    for key in ("text", "src_text", "content", "transcript"):
        value = segment.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _normalize_response_segments(
    segments: Any,
    offset_seconds: float,
    start_index: int,
) -> list[dict[str, Any]]:
    """Normalize model segment list to start/end seconds + SRT timestamps."""
    if not isinstance(segments, list):
        return []

    normalized: list[dict[str, Any]] = []
    for raw_segment in segments:
        if not isinstance(raw_segment, dict):
            continue

        start = _to_seconds(raw_segment.get("start_seconds"))
        if start is None:
            start = _to_seconds(raw_segment.get("start"))
        if start is None:
            start = _to_seconds(raw_segment.get("start_time"))

        end = _to_seconds(raw_segment.get("end_seconds"))
        if end is None:
            end = _to_seconds(raw_segment.get("end"))
        if end is None:
            end = _to_seconds(raw_segment.get("end_time"))

        if start is None or end is None:
            continue

        start = max(0.0, float(start) + offset_seconds)
        end = max(start, float(end) + offset_seconds)
        if end <= start:
            continue

        text = _segment_text(raw_segment)
        segment_index = raw_segment.get("index")
        if isinstance(segment_index, str) and segment_index.isdigit():
            segment_index = int(segment_index)

        normalized.append(
            {
                "index": segment_index,
                "start_seconds": round(start, 3),
                "end_seconds": round(end, 3),
                "start_time": _seconds_to_srt(start),
                "end_time": _seconds_to_srt(end),
                "text": text,
            }
        )

    normalized.sort(key=lambda seg: (float(seg["start_seconds"]), float(seg["end_seconds"])))
    if not normalized:
        return []

    next_index = start_index
    result: list[dict[str, Any]] = []
    for item in normalized:
        segment_index = item.get("index")
        if not isinstance(segment_index, int) or segment_index <= 0:
            segment_index = next_index
            next_index += 1
        result.append(
            {
                "index": segment_index,
                **{k: v for k, v in item.items() if k != "index"},
            }
        )

    return result


def _estimate_fallback_end(start_seconds: float, end_seconds: float, text: str) -> float:
    """Estimate segment end when chunk duration is unavailable."""
    if end_seconds > start_seconds:
        return end_seconds

    words = len((text or "").split())
    estimated_duration = max(0.8, words / 2.6 if words > 0 else 1.2)
    return start_seconds + estimated_duration


def _merge_chunked_transcription_responses(
    responses: list[Any],
    chunk_specs: list[_ChunkSpec],
    fallback_model: str,
    language: Optional[str],
) -> tuple[ModelResponse, list[dict[str, Any]]]:
    """Merge chunk-level responses into one model response and chunk metadata."""
    merged_text_parts: list[str] = []
    merged_segments: list[dict[str, Any]] = []
    chunked_audio: list[dict[str, Any]] = []
    segment_index = 1

    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    has_usage = False

    for spec, resp in zip(chunk_specs, responses):
        chunk_text = str(getattr(resp, "content", "") or "").strip()
        if chunk_text:
            merged_text_parts.append(chunk_text)

        usage = getattr(resp, "usage", None) or {}
        if usage:
            has_usage = True
            prompt_tokens += int(usage.get("prompt_tokens", 0) or 0)
            completion_tokens += int(usage.get("completion_tokens", 0) or 0)
            total_tokens += int(usage.get("total_tokens", 0) or 0)

        resp_metadata = getattr(resp, "metadata", None)
        raw_segments = resp_metadata.get("segments", []) if isinstance(resp_metadata, dict) else []
        normalized_segments = _normalize_response_segments(
            raw_segments,
            spec.start_seconds,
            segment_index,
        )
        if not normalized_segments and chunk_text:
            fallback_end = _estimate_fallback_end(spec.start_seconds, spec.end_seconds, chunk_text)
            normalized_segments = [
                {
                    "index": segment_index,
                    "start_seconds": round(spec.start_seconds, 3),
                    "end_seconds": round(fallback_end, 3),
                    "start_time": _seconds_to_srt(spec.start_seconds),
                    "end_time": _seconds_to_srt(fallback_end),
                    "text": chunk_text,
                }
            ]

        merged_segments.extend(normalized_segments)
        segment_index += len(normalized_segments)
        chunk_end = _estimate_fallback_end(spec.start_seconds, spec.end_seconds, chunk_text)
        chunked_audio.append(
            {
                "index": spec.index,
                "audio_path": spec.audio_path,
                "start_seconds": round(spec.start_seconds, 3),
                "end_seconds": round(chunk_end, 3),
                "start_time": _seconds_to_srt(spec.start_seconds),
                "end_time": _seconds_to_srt(chunk_end),
                "text": chunk_text,
                "segment_count": len(normalized_segments),
            }
        )

    merged_usage = None
    if has_usage:
        if total_tokens <= 0:
            total_tokens = prompt_tokens + completion_tokens
        merged_usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }

    merged_model = next(
        (getattr(resp, "model", None) for resp in responses if getattr(resp, "model", None)),
        fallback_model,
    )
    merged_text = "\n".join(part for part in merged_text_parts if part).strip()

    duration = None
    if merged_segments:
        duration = float(merged_segments[-1]["end_seconds"])
    elif chunk_specs:
        duration = max((spec.end_seconds for spec in chunk_specs), default=None)

    return (
        ModelResponse(
            content=merged_text,
            usage=merged_usage,
            model=merged_model,
            metadata={
                "segments": merged_segments,
                "language": language,
                "duration": duration,
                "chunk_count": len(chunk_specs),
            },
        ),
        chunked_audio,
    )


@ToolRegistry.register
class TranscribeTool(BaseTool):
    """ASR transcription tool."""

    name = "transcribe"
    description = "Transcribe audio to text using the configured ASR model"
    parameters = [
        ToolParameter(
            name="audio_path",
            type="string",
            description="Path to the audio file",
        ),
        ToolParameter(
            name="language",
            type="string",
            description="Source language code (e.g., 'en', 'zh')",
            required=False,
        ),
        ToolParameter(
            name="prompt",
            type="string",
            description="Optional prompt to guide transcription",
            required=False,
        ),
        ToolParameter(
            name="model",
            type="string",
            description="Optional model override for the chosen provider",
            required=False,
        ),
        ToolParameter(
            name="provider",
            type="string",
            description="ASR provider to use (e.g., 'qwen', 'openai', 'google')",
            required=False,
        ),
    ]

    def __init__(
        self,
        audio_model: Optional[AudioModelInterface] = None,
        model_config: Optional[ModelConfig] = None,
    ):
        super().__init__()
        self._audio_model = audio_model
        self._model_config = model_config or _get_default_audio_config()

    async def execute(
        self,
        audio_path: str,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        chunks: Optional[list[dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute speech recognition."""
        try:
            resolved_provider, provider_model = _parse_provider_spec(provider)
            resolved_model = _normalize_model_override(model or provider_model, resolved_provider)
            if resolved_model is None:
                resolved_model = _MODEL_FALLBACK_BY_PROVIDER.get(
                    resolved_provider, _MODEL_FALLBACK_BY_PROVIDER["openai"]
                )
            normalized_language = _normalize_language_code(language)
            model_config = _get_default_audio_config(
                provider=resolved_provider,
                model=resolved_model,
            )

            if (
                self._audio_model is not None
                and self._model_config.provider == model_config.provider
                and self._model_config.model_name == model_config.model_name
            ):
                model_instance = self._audio_model
            else:
                model_instance = ModelRegistry.get(model_config, ModelType.AUDIO)

            prepared_audio_path, temp_audio_path = _prepare_audio_input(
                audio_path, resolved_provider
            )
            chunk_dir: Optional[str] = None
            chunked_audio: list[dict[str, Any]] = []

            try:
                provided_chunk_specs = _normalize_chunk_inputs(chunks or [])
                chunk_specs: list[_ChunkSpec] = []
                chunk_manifest_inferred = False

                if provided_chunk_specs:
                    chunk_specs = provided_chunk_specs
                else:
                    inferred_chunks = _infer_chunk_specs_from_segment_filenames(prepared_audio_path)
                    if inferred_chunks:
                        chunk_specs = inferred_chunks
                        chunk_manifest_inferred = True
                    elif resolved_provider == "qwen":
                        split_paths, split_chunk_dir = _split_audio_into_chunks(prepared_audio_path)
                        chunk_specs = _build_chunk_specs_from_paths(split_paths)
                        chunk_dir = split_chunk_dir
                    else:
                        duration = _probe_audio_duration_seconds(prepared_audio_path) or 0.0
                        chunk_specs = [
                            _ChunkSpec(
                                index=1,
                                audio_path=prepared_audio_path,
                                start_seconds=0.0,
                                end_seconds=duration,
                            )
                        ]

                use_chunk_loop = (
                    bool(provided_chunk_specs) or len(chunk_specs) > 1 or chunk_manifest_inferred
                )
                if use_chunk_loop:
                    chunk_responses: list[ModelResponse] = []
                    for chunk_spec in chunk_specs:
                        chunk_response = await model_instance.transcribe(
                            audio=chunk_spec.audio_path,
                            language=normalized_language,
                            prompt=prompt,
                            **kwargs,
                        )
                        chunk_responses.append(chunk_response)

                    response, chunked_audio = _merge_chunked_transcription_responses(
                        chunk_responses,
                        chunk_specs,
                        fallback_model=model_config.model_name,
                        language=normalized_language,
                    )
                else:
                    response = await model_instance.transcribe(
                        audio=prepared_audio_path,
                        language=normalized_language,
                        prompt=prompt,
                        **kwargs,
                    )

                    metadata = response.metadata if isinstance(response.metadata, dict) else {}
                    normalized_segments = _normalize_response_segments(
                        metadata.get("segments", []),
                        0.0,
                        1,
                    )
                    transcript_text = str(getattr(response, "content", "") or "").strip()
                    if not normalized_segments and transcript_text:
                        response_duration = _to_seconds(metadata.get("duration"))
                        if response_duration is None or response_duration <= 0:
                            response_duration = (
                                _probe_audio_duration_seconds(prepared_audio_path) or 0.0
                            )
                        fallback_end = _estimate_fallback_end(
                            0.0, response_duration, transcript_text
                        )
                        normalized_segments = [
                            {
                                "index": 1,
                                "start_seconds": 0.0,
                                "end_seconds": round(fallback_end, 3),
                                "start_time": _seconds_to_srt(0.0),
                                "end_time": _seconds_to_srt(fallback_end),
                                "text": transcript_text,
                            }
                        ]

                    if normalized_segments:
                        metadata["segments"] = normalized_segments
                        metadata["duration"] = float(normalized_segments[-1]["end_seconds"])
                        if normalized_language is not None:
                            metadata["language"] = normalized_language
                    else:
                        metadata.setdefault("segments", [])
                    response.metadata = metadata
            finally:
                if temp_audio_path:
                    try:
                        Path(temp_audio_path).unlink(missing_ok=True)
                    except Exception:
                        pass
                _cleanup_chunk_dir(chunk_dir)

            response_metadata = response.metadata if isinstance(response.metadata, dict) else {}
            return ToolResult.ok(
                data={
                    "text": response.content,
                    "segments": response_metadata.get("segments", []),
                    "language": response_metadata.get("language"),
                    "duration": response_metadata.get("duration"),
                    "chunked_audio": chunked_audio,
                },
                model=response.model,
                chunk_count=len(chunked_audio),
            )
        except Exception as e:
            err_msg = str(e)
            if "InvalidApiKey" in err_msg or "Invalid API-key" in err_msg:
                return ToolResult.fail(
                    "Transcription failed: DashScope API key invalid. "
                    "Set a valid AKI_DASHSCOPE_API_KEY (or DASHSCOPE_API_KEY)."
                )
            return ToolResult.fail(f"Transcription failed: {err_msg}")
