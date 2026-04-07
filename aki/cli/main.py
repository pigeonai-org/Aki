"""
Aki CLI Entry Point

Command-line interface for Aki operations.
"""

import asyncio
import json
import os
import re
import shutil
import subprocess
import socket
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import typer
from rich.console import Console
from rich.panel import Panel

from aki import __version__
from aki.config import get_settings

app = typer.Typer(
    name="aki",
    help="Aki — an agentic system with personality and autonomy",
    add_completion=False,
)
memory_app = typer.Typer(help="Manage long-term memory")
app.add_typer(memory_app, name="memory")
console = Console()


def _pipeline_log(verbose: bool, message: str) -> None:
    """Emit deterministic subtitle pipeline logs in verbose mode."""
    if verbose:
        console.print(message, style="dim", markup=False)


def _resolve_api_key_for_provider(settings, provider: str) -> Optional[str]:
    """Resolve configured API key for a model provider."""
    if provider == "openai":
        return settings.openai_api_key
    if provider == "anthropic":
        return settings.anthropic_api_key
    if provider == "google":
        return settings.google_api_key
    if provider == "qwen":
        return settings.dashscope_api_key
    return None


def _normalize_http_url(raw_url: Optional[str]) -> Optional[str]:
    """Normalize API endpoint URL and ensure a scheme exists."""
    if not raw_url:
        return None

    value = raw_url.strip()
    if not value:
        return None

    if "://" in value:
        return value
    return f"https://{value}"


def _check_endpoint_dns_reachability(endpoint_url: str) -> Optional[str]:
    """Return a short description if DNS/network resolution fails."""
    resolved_url = _normalize_http_url(endpoint_url)
    if not resolved_url:
        return "Endpoint URL is missing."

    parsed = urlparse(resolved_url)
    if not parsed.hostname:
        return f"Invalid endpoint URL: {endpoint_url}"

    try:
        socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except OSError as exc:
        return (
            f"Unable to resolve '{parsed.hostname}' for endpoint '{endpoint_url}'. "
            "Check DNS/network access and proxy settings."
            f" (detail: {exc})"
        )
    return None


def _preflight_llm_connectivity(llm_config, settings) -> None:
    """Fail fast for common network setup problems before running async pipeline."""
    if llm_config.provider != "openai":
        return

    endpoint = llm_config.base_url or settings.openai_base_url or "https://api.openai.com/v1"
    dns_error = _check_endpoint_dns_reachability(endpoint)
    if dns_error:
        raise RuntimeError(
            "LLM provider network validation failed before task execution. "
            + dns_error
            + " Verify outbound internet access to provider endpoints."
        )


def _build_runtime_memory_manager():
    """Create memory manager using current settings."""
    from aki.runtime import build_memory_manager

    return build_memory_manager(get_settings())


def _build_task_output_dir(video_path: str) -> tuple[str, Path]:
    """Create output directory path under outputs/ using a task-style id."""
    video_name = Path(video_path).stem or "video"
    task_id = f"Translate {video_name}"
    safe_task_id = task_id.replace("/", "_").replace("\\", "_")
    safe_task_id = re.sub(r"\s+", "_", safe_task_id).strip("_")
    if not safe_task_id:
        safe_task_id = "Translate_video"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    task_dir = Path("outputs") / f"{safe_task_id}_{timestamp}"
    task_dir.mkdir(parents=True, exist_ok=True)
    return task_id, task_dir


def _write_json(path: Path, payload: Any) -> None:
    """Write JSON payload with stable formatting."""
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _probe_media_duration_seconds(media_path: str) -> Optional[float]:
    """Probe media duration with ffprobe when available."""
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
        media_path,
    ]

    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        duration = float((completed.stdout or "").strip())
        return duration if duration > 0 else None
    except Exception:
        return None


def _seconds_to_srt(seconds: float) -> str:
    """Convert seconds to HH:MM:SS,mmm."""
    total_ms = max(0, int(round(seconds * 1000)))
    hours = total_ms // 3600000
    total_ms %= 3600000
    minutes = total_ms // 60000
    total_ms %= 60000
    secs = total_ms // 1000
    ms = total_ms % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _srt_to_seconds(value: Any) -> Optional[float]:
    """Parse HH:MM:SS,mmm (or numeric string) into seconds."""
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return max(0.0, float(value))

    text = str(value).strip()
    if not text:
        return None

    if ":" not in text:
        try:
            return max(0.0, float(text))
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
            sec_str, ms_str = sec_part.split(",", 1)
            secs = int(sec_str)
            millis = int(ms_str[:3].ljust(3, "0"))
        else:
            secs = int(sec_part)
            millis = 0
        return max(0.0, hours * 3600 + minutes * 60 + secs + millis / 1000.0)
    except Exception:
        return None


def _extract_transcribe_segments(transcribe_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize transcribe segment payload for subtitle-template creation."""
    raw_segments = transcribe_data.get("segments") or []
    normalized_segments: list[dict[str, Any]] = []
    if not isinstance(raw_segments, list):
        return normalized_segments

    for item in raw_segments:
        if not isinstance(item, dict):
            continue

        start_seconds = _srt_to_seconds(item.get("start_seconds"))
        if start_seconds is None:
            start_seconds = _srt_to_seconds(item.get("start_time"))
        if start_seconds is None:
            start_seconds = _srt_to_seconds(item.get("start"))

        end_seconds = _srt_to_seconds(item.get("end_seconds"))
        if end_seconds is None:
            end_seconds = _srt_to_seconds(item.get("end_time"))
        if end_seconds is None:
            end_seconds = _srt_to_seconds(item.get("end"))

        if start_seconds is None or end_seconds is None or end_seconds <= start_seconds:
            continue

        text = str(
            item.get("text")
            or item.get("src_text")
            or item.get("content")
            or item.get("transcript")
            or ""
        ).strip()
        if not text:
            continue

        normalized_segments.append(
            {
                "start_seconds": float(start_seconds),
                "end_seconds": float(end_seconds),
                "text": text,
            }
        )

    normalized_segments.sort(key=lambda seg: (seg["start_seconds"], seg["end_seconds"]))
    return normalized_segments


def _split_transcript_to_chunks(text: str) -> list[str]:
    """Split transcript text into readable subtitle chunks."""
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if not normalized:
        return []

    sentence_chunks = re.split(r"(?<=[.!?。！？])\s+", normalized)
    chunks: list[str] = []
    for sentence in sentence_chunks:
        sentence = sentence.strip()
        if not sentence:
            continue

        if len(sentence) <= 84:
            chunks.append(sentence)
            continue

        comma_splits = re.split(r"(?<=[,;:，；：])\s*", sentence)
        if len(comma_splits) > 1:
            for piece in comma_splits:
                piece = piece.strip()
                if piece:
                    chunks.append(piece)
            continue

        words = sentence.split()
        current: list[str] = []
        current_len = 0
        for word in words:
            word_len = len(word) + 1
            if current and current_len + word_len > 72:
                chunks.append(" ".join(current))
                current = [word]
                current_len = len(word)
            else:
                current.append(word)
                current_len += word_len
        if current:
            chunks.append(" ".join(current))

    return chunks or [normalized]


def _build_template_subtitles(
    transcript_text: str, duration_seconds: Optional[float]
) -> list[dict[str, Any]]:
    """Build subtitle template entries from transcript text."""
    chunks = _split_transcript_to_chunks(transcript_text)
    if not chunks:
        return []

    if duration_seconds is None or duration_seconds <= 0:
        duration_seconds = max(2.0, len(transcript_text.split()) / 2.5)

    total_chars = max(1, sum(len(chunk) for chunk in chunks))
    total_duration_ms = max(1, int(round(float(duration_seconds) * 1000)))
    subtitles: list[dict[str, Any]] = []
    start_ms = 0
    cumulative_chars = 0
    for idx, chunk in enumerate(chunks, start=1):
        cumulative_chars += len(chunk)
        if idx == len(chunks):
            end_ms = total_duration_ms
        else:
            end_ms = int(round(total_duration_ms * (cumulative_chars / total_chars)))
            if end_ms <= start_ms:
                end_ms = min(total_duration_ms, start_ms + 1)

        subtitles.append(
            {
                "index": idx,
                "start_time": _seconds_to_srt(start_ms / 1000.0),
                "end_time": _seconds_to_srt(end_ms / 1000.0),
                "text": chunk,
                "src_text": chunk,
                "translation": "",
            }
        )
        start_ms = end_ms

    if subtitles and subtitles[-1]["end_time"] != _seconds_to_srt(total_duration_ms / 1000.0):
        subtitles[-1]["end_time"] = _seconds_to_srt(total_duration_ms / 1000.0)
    return subtitles


def _build_template_subtitles_from_segments(
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build subtitle template entries from normalized ASR segments."""
    subtitles: list[dict[str, Any]] = []
    for idx, seg in enumerate(segments, start=1):
        start_seconds = float(seg["start_seconds"])
        end_seconds = float(seg["end_seconds"])
        if end_seconds <= start_seconds:
            continue
        text = str(seg.get("text") or "").strip()
        if not text:
            continue

        subtitles.append(
            {
                "index": idx,
                "start_time": _seconds_to_srt(start_seconds),
                "end_time": _seconds_to_srt(end_seconds),
                "text": text,
                "src_text": text,
                "translation": "",
            }
        )
    return subtitles


def resolve_quality_profile(profile: str) -> str:
    return profile if profile in {"fast", "balanced", "quality"} else "balanced"


def profile_defaults(profile: str) -> dict[str, Any]:
    return {
        "vad_min_segment_seconds": 1.0,
        "vad_max_chunk_seconds": 15.0,
        "frame_interval_sec": 5,
        "max_frames": 20,
        "vision_detail": "high",
        "split_threshold": 80,
        "proofread_batch_size": 20,
        "editor_context_window": 5,
    }


async def _run_subtitle_pipeline(
    video: str,
    source_lang: str,
    target_lang: str,
    enable_vision: bool,
    output_name: Optional[str],
    quality_profile: str = "balanced",
    verbose: bool = False,
) -> dict[str, Any]:
    """Run deterministic subtitle pipeline and persist artifacts under outputs/."""
    from aki.runtime import build_memory_manager
    from aki.tools import ToolRegistry

    task_id, task_dir = _build_task_output_dir(video)
    settings = get_settings()
    memory = build_memory_manager(settings)
    default_audio_spec = settings.default_audio
    resolved_quality = resolve_quality_profile(quality_profile)
    quality_defaults = profile_defaults(resolved_quality)
    video_path = str(Path(video).expanduser())
    video_name = Path(video_path).name

    _write_json(
        task_dir / "task_meta.json",
        {
            "task_id": task_id,
            "video": video_path,
            "source_language": source_lang,
            "target_language": target_lang,
            "vision_enabled": enable_vision,
            "quality_profile": resolved_quality,
            "default_audio": default_audio_spec,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    _pipeline_log(
        verbose,
        f"[audio_analyzer] start | input={video_path} | quality={resolved_quality}",
    )

    audio_extract_tool = ToolRegistry.get("audio_extract")
    extracted_audio_path = str(task_dir / f"{Path(video_name).stem}.asr.mp3")
    _pipeline_log(verbose, "[audio_analyzer] audio_extract -> running")
    audio_extract_result = await audio_extract_tool(
        video_path=video_path,
        output_path=extracted_audio_path,
    )
    _write_json(task_dir / "audio_extract_result.json", audio_extract_result.model_dump())
    if not audio_extract_result.success:
        raise RuntimeError(audio_extract_result.error or "audio_extract failed")

    extracted_audio_path = str(audio_extract_result.data.get("audio_path") or extracted_audio_path)
    _pipeline_log(verbose, f"[audio_analyzer] audio_extract -> ok | audio={extracted_audio_path}")
    await memory.remember(
        content=f"audio_extract completed: {extracted_audio_path}",
        type="observation",
        task_id=task_id,
        stage="audio_extract",
        audio_path=extracted_audio_path,
    )

    chunk_manifest: list[dict[str, Any]] = []
    audio_vad_tool = ToolRegistry.get("audio_vad")
    _pipeline_log(verbose, "[audio_analyzer] audio_vad -> running")
    audio_vad_result = await audio_vad_tool(
        audio_path=extracted_audio_path,
        output_dir=str(task_dir / "audio_chunks"),
        min_segment_seconds=float(quality_defaults["vad_min_segment_seconds"]),
        max_chunk_seconds=float(quality_defaults["vad_max_chunk_seconds"]),
    )
    _write_json(task_dir / "audio_vad_result.json", audio_vad_result.model_dump())
    if audio_vad_result.success and isinstance(audio_vad_result.data, dict):
        raw_chunks = audio_vad_result.data.get("chunks") or []
        if isinstance(raw_chunks, list):
            chunk_manifest = [chunk for chunk in raw_chunks if isinstance(chunk, dict)]
        _pipeline_log(
            verbose,
            f"[audio_analyzer] audio_vad -> ok | chunks={len(chunk_manifest)}",
        )
        if chunk_manifest:
            await memory.remember(
                content=f"audio_vad produced {len(chunk_manifest)} chunks",
                type="observation",
                task_id=task_id,
                stage="audio_vad",
                chunked_audio=chunk_manifest,
            )

    if enable_vision:
        frame_tool = ToolRegistry.get("video_extract_frames")
        _pipeline_log(verbose, "[video_analyzer] video_extract_frames -> running")
        frame_result = await frame_tool(
            video_path=video_path,
            frame_interval_sec=int(quality_defaults["frame_interval_sec"]),
            max_frames=int(quality_defaults["max_frames"]),
        )
        _write_json(task_dir / "vision_frames_result.json", frame_result.model_dump())

        if frame_result.success and isinstance(frame_result.data, dict):
            frame_paths = frame_result.data.get("frames") or []
            _pipeline_log(
                verbose, f"[video_analyzer] video_extract_frames -> ok | frames={len(frame_paths)}"
            )
            if frame_paths:
                vision_tool = ToolRegistry.get("vision_analyze")
                _pipeline_log(verbose, "[video_analyzer] vision_analyze -> running")
                vision_result = await vision_tool(
                    images=frame_paths,
                    prompt="Summarize scene context relevant to subtitle translation.",
                    detail=str(quality_defaults["vision_detail"]),
                )
                _write_json(task_dir / "vision_analysis_result.json", vision_result.model_dump())
                if vision_result.success:
                    _pipeline_log(verbose, "[video_analyzer] vision_analyze -> ok")
                else:
                    _pipeline_log(verbose, "[video_analyzer] vision_analyze -> failed")

    transcribe_tool = ToolRegistry.get("transcribe")
    _pipeline_log(verbose, "[audio_analyzer] transcribe -> running")
    transcribe_result = await transcribe_tool(
        audio_path=extracted_audio_path,
        language=source_lang,
        provider=default_audio_spec,
        chunks=chunk_manifest or None,
    )
    _write_json(task_dir / "transcribe_result.json", transcribe_result.model_dump())
    if not transcribe_result.success:
        raise RuntimeError(transcribe_result.error or "transcribe failed")
    _pipeline_log(verbose, "[audio_analyzer] transcribe -> ok")

    transcribe_data = transcribe_result.data or {}
    transcript_text = str((transcribe_data.get("text") or "")).strip()
    (task_dir / "transcript.txt").write_text(transcript_text, encoding="utf-8")
    if not transcript_text:
        raise RuntimeError("Transcription is empty; cannot continue subtitle translation.")

    transcribe_chunked_audio = transcribe_data.get("chunked_audio") or []
    if transcribe_chunked_audio:
        await memory.remember(
            content=f"transcribe processed {len(transcribe_chunked_audio)} chunks",
            type="result",
            task_id=task_id,
            stage="transcribe",
            chunked_audio=transcribe_chunked_audio,
        )

    normalized_segments = _extract_transcribe_segments(transcribe_data)
    duration_seconds = _probe_media_duration_seconds(
        extracted_audio_path
    ) or _probe_media_duration_seconds(video_path)
    if normalized_segments:
        subtitle_template = _build_template_subtitles_from_segments(normalized_segments)
    else:
        subtitle_template = _build_template_subtitles(transcript_text, duration_seconds)

    _write_json(
        task_dir / "subtitle_template.json",
        {
            "count": len(subtitle_template),
            "subtitles": subtitle_template,
        },
    )
    if not subtitle_template:
        raise RuntimeError("Failed to build subtitle template from transcription.")

    subtitle_translate_tool = ToolRegistry.get("subtitle_translate")
    _pipeline_log(verbose, "[translator] subtitle_translate -> running")
    subtitle_translation_result = await subtitle_translate_tool(
        subtitles=subtitle_template,
        source_language=source_lang,
        target_language=target_lang,
        domain="general",
        split_threshold=int(quality_defaults["split_threshold"]),
    )
    _write_json(
        task_dir / "subtitle_translation_result.json", subtitle_translation_result.model_dump()
    )
    if not subtitle_translation_result.success:
        raise RuntimeError(subtitle_translation_result.error or "subtitle_translate failed")
    _pipeline_log(verbose, "[translator] subtitle_translate -> ok")

    translated_subtitles = (subtitle_translation_result.data or {}).get("subtitles") or []
    if not translated_subtitles:
        raise RuntimeError("Subtitle translation returned empty subtitles.")

    subtitle_proofread_tool = ToolRegistry.get("subtitle_proofread")
    _pipeline_log(verbose, "[proofreader] subtitle_proofread -> running")
    subtitle_proofread_result = await subtitle_proofread_tool(
        subtitles=translated_subtitles,
        target_language=target_lang,
        batch_size=int(quality_defaults["proofread_batch_size"]),
    )
    _write_json(task_dir / "subtitle_proofread_result.json", subtitle_proofread_result.model_dump())
    _pipeline_log(
        verbose,
        "[proofreader] subtitle_proofread -> "
        + ("ok" if subtitle_proofread_result.success else "failed"),
    )

    review_suggestions: list[dict[str, Any]] = []
    if subtitle_proofread_result.success and isinstance(subtitle_proofread_result.data, dict):
        raw_suggestions = subtitle_proofread_result.data.get("suggestions") or []
        if isinstance(raw_suggestions, list):
            review_suggestions = [item for item in raw_suggestions if isinstance(item, dict)]

    subtitle_edit_tool = ToolRegistry.get("subtitle_edit")
    _pipeline_log(verbose, "[editor] subtitle_edit -> running")
    subtitle_edit_result = await subtitle_edit_tool(
        subtitles=translated_subtitles,
        domain="general",
        context_window=int(quality_defaults["editor_context_window"]),
        suggestions=review_suggestions,
    )
    _write_json(task_dir / "subtitle_edit_result.json", subtitle_edit_result.model_dump())
    _pipeline_log(
        verbose,
        "[editor] subtitle_edit -> " + ("ok" if subtitle_edit_result.success else "failed"),
    )

    final_subtitles = translated_subtitles
    if subtitle_edit_result.success and isinstance(subtitle_edit_result.data, dict):
        edited_subtitles = subtitle_edit_result.data.get("subtitles") or []
        if isinstance(edited_subtitles, list) and edited_subtitles:
            final_subtitles = edited_subtitles

    requested_name = (
        Path(output_name).name if output_name else f"{Path(video_name).stem}.{target_lang}.srt"
    )
    final_srt_path = task_dir / requested_name

    srt_write_tool = ToolRegistry.get("srt_write")
    _pipeline_log(verbose, f"[io] srt_write -> running | output={final_srt_path}")
    srt_write_result = await srt_write_tool(
        file_path=str(final_srt_path),
        subtitles=final_subtitles,
        prefer_translation=True,
    )
    _write_json(task_dir / "srt_write_result.json", srt_write_result.model_dump())
    if not srt_write_result.success:
        raise RuntimeError(srt_write_result.error or "srt_write failed")
    _pipeline_log(verbose, "[io] srt_write -> ok")

    memory_snapshot = await memory.recall(task_id=task_id, limit=200)
    _write_json(
        task_dir / "memory_snapshot.json",
        {
            "count": len(memory_snapshot),
            "memories": [item.model_dump(mode="json") for item in memory_snapshot],
        },
    )
    _pipeline_log(verbose, f"[pipeline] complete | task_dir={task_dir.resolve()}")

    return {
        "task_id": task_id,
        "task_dir": str(task_dir.resolve()),
        "transcript_path": str((task_dir / "transcript.txt").resolve()),
        "template_path": str((task_dir / "subtitle_template.json").resolve()),
        "translation_path": str((task_dir / "subtitle_translation_result.json").resolve()),
        "proofread_path": str((task_dir / "subtitle_proofread_result.json").resolve()),
        "edit_path": str((task_dir / "subtitle_edit_result.json").resolve()),
        "memory_path": str((task_dir / "memory_snapshot.json").resolve()),
        "srt_path": str(final_srt_path.resolve()),
        "result": {
            "subtitles": final_subtitles,
            "count": len(final_subtitles),
            "review_suggestions": review_suggestions,
            "quality_profile": resolved_quality,
        },
    }


@app.command()
def version() -> None:
    """Show the Aki version."""
    console.print(f"[bold blue]Aki[/bold blue] version [green]{__version__}[/green]")


@app.command()
def config() -> None:
    """Show current configuration."""
    settings = get_settings()
    console.print("[bold]Current Configuration:[/bold]")
    console.print(f"  Default LLM: {settings.default_llm}")
    console.print(f"  Default VLM: {settings.default_vlm}")
    console.print(f"  Default Audio: {settings.default_audio}")
    console.print(f"  Default Embedding: {settings.default_embedding}")
    console.print(f"  Max Agents per Task: {settings.agent.max_agents_per_task}")
    console.print(f"  Max Agent Depth: {settings.agent.max_agent_depth}")
    console.print(f"  Memory Window Size: {settings.memory.window_size}")
    console.print(f"  Memory Backend: {settings.memory.long_term_backend}")
    console.print(f"  Long-term Enabled: {settings.memory.long_term_enabled}")
    console.print(f"  Short-term Per Task: {settings.memory.short_term_max_items_per_task}")
    console.print(f"  Long-term Top-K: {settings.memory.long_term_top_k}")

    # Check API keys
    console.print("\n[bold]API Keys:[/bold]")
    console.print(
        f"  OpenAI: {'[green]configured[/green]' if settings.openai_api_key else '[red]not set[/red]'}"
    )
    console.print(
        f"  Anthropic: {'[green]configured[/green]' if settings.anthropic_api_key else '[red]not set[/red]'}"
    )
    console.print(
        f"  Google: {'[green]configured[/green]' if settings.google_api_key else '[red]not set[/red]'}"
    )
    console.print(
        f"  DashScope: {'[green]configured[/green]' if settings.dashscope_api_key else '[red]not set[/red]'}"
    )
    console.print(
        f"  Pyannote: {'[green]configured[/green]' if settings.pyannote_api_key else '[red]not set[/red]'}"
    )


@app.command()
def run(
    task: str = typer.Argument(..., help="The task to execute"),
    agent: str = typer.Option("main", "--agent", "-a", help="Agent type to use"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
) -> None:
    """Run a task with the Aki agent system."""
    console.print(
        Panel(
            f"[bold]Task:[/bold] {task}\n[bold]Agent:[/bold] {agent}",
            title="Aki",
            border_style="blue",
        )
    )

    if verbose:
        console.print("[dim]Verbose mode enabled[/dim]")

    # Check for API key required by default LLM provider
    settings = get_settings()
    from aki.models import ModelConfig

    llm_config = ModelConfig.from_string(settings.default_llm)
    llm_api_key = _resolve_api_key_for_provider(settings, llm_config.provider)
    if llm_api_key is None:
        console.print(
            f"[red]Error: API key not configured for LLM provider '{llm_config.provider}'.[/red]"
        )
        if llm_config.provider == "openai":
            console.print("Set AKI_OPENAI_API_KEY or OPENAI_API_KEY in environment/.env.")
        elif llm_config.provider == "anthropic":
            console.print("Set AKI_ANTHROPIC_API_KEY or ANTHROPIC_API_KEY in environment/.env.")
        elif llm_config.provider == "google":
            console.print("Set AKI_GOOGLE_API_KEY or GOOGLE_API_KEY in environment/.env.")
        elif llm_config.provider == "qwen":
            console.print("Set AKI_DASHSCOPE_API_KEY or DASHSCOPE_API_KEY in environment/.env.")
        raise typer.Exit(1)

    # Run the task
    try:
        _preflight_llm_connectivity(llm_config, settings)
        result = asyncio.run(_run_task(task, agent, verbose))
        console.print("\n[bold green]Result:[/bold green]")
        console.print(result)
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        if verbose and not str(e).startswith("LLM provider network validation failed"):
            import traceback

            console.print(traceback.format_exc())
        raise typer.Exit(1)


async def _run_task(task: str, agent_type: str, verbose: bool) -> Any:
    """Internal async task runner."""
    from aki.agent import AgentOrchestrator, OrchestratorConfig
    from aki.agent.logger import set_verbose
    from aki.config import get_settings
    from aki.models import ModelConfig, ModelRegistry, ModelType
    from aki.runtime import build_memory_manager

    # Enable verbose logging if requested
    set_verbose(verbose)

    settings = get_settings()

    # Create LLM
    llm_config = ModelConfig.from_string(settings.default_llm)
    llm_config.api_key = _resolve_api_key_for_provider(settings, llm_config.provider)
    if llm_config.provider == "openai" and settings.openai_base_url:
        llm_config.base_url = settings.openai_base_url
    _preflight_llm_connectivity(llm_config, settings)
    llm = ModelRegistry.get(llm_config, ModelType.LLM)

    # Create memory manager
    memory = build_memory_manager(settings)

    # Create orchestrator
    config = OrchestratorConfig(
        max_agents_per_task=settings.agent.max_agents_per_task,
        max_agent_depth=settings.agent.max_agent_depth,
        default_agent_type=agent_type,
    )

    orchestrator = AgentOrchestrator(
        config=config,
        llm=llm,
        memory=memory,
    )

    # Run the task
    result = await orchestrator.run_task(task)

    return result


@app.command()
def chat(
    llm: str = typer.Option("", "--llm", help="LLM override (e.g. openai:gpt-4o)"),
    mcp: str = typer.Option("", "--mcp", help="MCP server URL to connect (e.g. http://localhost:8000/mcp)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
) -> None:
    """Start an interactive multi-turn chat session."""
    settings = get_settings()
    from aki.models import ModelConfig

    llm_config_str = llm or settings.default_llm
    llm_model_config = ModelConfig.from_string(llm_config_str)
    llm_api_key = _resolve_api_key_for_provider(settings, llm_model_config.provider)
    if llm_api_key is None:
        console.print(f"[red]Error: API key not configured for '{llm_model_config.provider}'.[/red]")
        raise typer.Exit(1)

    # ── Welcome screen ──
    _print_welcome(llm_model_config, mcp)

    # Check if this is a restart
    if os.environ.pop("AKI_RESTARTED", None):
        console.print("[green]Restarted successfully.[/green]\n")

    try:
        _preflight_llm_connectivity(llm_model_config, settings)
        asyncio.run(_chat_loop(llm_config_str, verbose, mcp_url=mcp or None))
    except KeyboardInterrupt:
        console.print("\n[dim]Bye.[/dim]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if verbose:
            import traceback

            console.print(traceback.format_exc())
        raise typer.Exit(1)


def _print_welcome(model_config: Any, mcp_url: str = "") -> None:
    """Print the Claude Code-style welcome screen."""
    import os
    from rich.columns import Columns
    from rich.panel import Panel
    from rich.text import Text
    from rich.align import Align

    width = shutil.get_terminal_size().columns
    cwd = os.getcwd()
    home = os.path.expanduser("~")
    if cwd.startswith(home):
        cwd_display = "~" + cwd[len(home):]
    else:
        cwd_display = cwd

    # Detect active persona
    import json as _json
    _active_persona = "aki"
    _persona_display = "aki"
    _state_file = Path(".aki/personality/active.json")
    if _state_file.exists():
        try:
            _active_persona = _json.loads(_state_file.read_text(encoding="utf-8")).get("active", "aki")
        except Exception:
            pass
    try:
        from aki.personality.registry import load_personality as _lp
        _p = _lp(_active_persona)
        if _p:
            _persona_display = _p.display_name
    except Exception:
        pass

    # Build two-column layout like Claude Code
    # Left: centered greeting + avatar + model info
    # Right: tips + persona status
    left = Text(justify="center")
    left.append("\n")
    left.append("Welcome to Aki!\n\n", style="bold")
    left.append("       ▄▀█ █▄▀ █\n", style="bold blue")
    left.append("       █▀█ █ █ █\n", style="bold blue")
    left.append("\n")
    left.append(f"{model_config.provider}:{model_config.model_name}\n", style="dim")
    left.append(f"Persona: {_persona_display}\n", style="dim")
    left.append(f"{cwd_display}\n", style="dim")

    right = Text()
    right.append("\n")
    right.append("Getting started\n", style="bold")
    right.append("  /persona       List or switch persona\n", style="dim")
    right.append("  /help          Show all commands\n", style="dim")
    right.append("─" * 40 + "\n", style="dim")
    right.append("Active persona\n", style="bold")
    right.append(f"  {_persona_display}", style="cyan")
    if _active_persona != _persona_display:
        right.append(f" ({_active_persona})", style="dim")
    right.append("\n")
    if mcp_url:
        right.append(f"  MCP: {mcp_url}\n", style="dim cyan")

    panel_content = Columns([left, right], column_first=True, padding=(0, 4))
    console.print(Panel(
        panel_content,
        border_style="blue",
        title=f"[bold]Aki[/bold] v{__version__}",
        title_align="left",
    ))
    console.print()


def _handle_persona_command(arg: str, con: Console) -> None:
    """Handle /persona [name] — list personas or switch active one."""
    import json as _json
    from pathlib import Path as _Path

    from aki.personality.registry import discover_personalities, load_personality

    if not arg:
        # List all personas + show active
        personas = discover_personalities()
        active_name = "aki"
        state_file = _Path(".aki/personality/active.json")
        if state_file.exists():
            try:
                active_name = _json.loads(state_file.read_text(encoding="utf-8")).get("active", "aki")
            except Exception:
                pass

        con.print()
        if not personas:
            con.print("[dim]No personas found.[/dim]")
        else:
            for p in personas:
                marker = "[bold cyan]●[/bold cyan]" if p.name == active_name else "[dim]○[/dim]"
                con.print(f"  {marker} [bold]{p.name}[/bold]  [dim]{p.description}[/dim]")
                con.print(f"    [dim]MBTI: {p.mbti}  Language: {p.language}  Traits: {', '.join(p.traits[:4])}[/dim]")
        con.print()
        con.print("[dim]  Usage: /persona <name> to switch[/dim]")
        con.print()
        return

    # Switch persona
    persona = load_personality(arg)
    if persona is None:
        available = [p.name for p in discover_personalities()]
        con.print(f"[red]Persona '{arg}' not found.[/red] Available: {', '.join(available)}")
        return

    # Write active.json
    state_dir = _Path(".aki/personality")
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "active.json"
    state_file.write_text(
        _json.dumps({"active": persona.name}, ensure_ascii=False),
        encoding="utf-8",
    )
    con.print(f"\n  Switched to [bold]{persona.display_name}[/bold] ({persona.mbti})")
    con.print(f"  [dim]{persona.description}[/dim]\n")


def _handle_model_command(arg: str, state: Any, con: Console) -> None:
    """Handle /model [provider:model] — show current or switch model mid-session."""
    if not arg:
        # Show current model
        agent = getattr(state, "agent", None)
        if agent and agent.llm:
            llm = agent.llm
            provider = getattr(llm, "provider", "?")
            model = getattr(llm, "model_name", "?")
            # Some providers store the model name differently
            if provider == "?" and hasattr(llm, "_model"):
                model = llm._model
            if hasattr(llm, "config"):
                cfg = llm.config
                provider = getattr(cfg, "provider", provider)
                model = getattr(cfg, "model_name", model)
            con.print(f"\n  [dim]Current model:[/dim] [bold]{provider}:{model}[/bold]\n")
        else:
            con.print("\n  [dim]No model info available.[/dim]\n")
        return

    # Switch model
    from aki.api.session_manager import _build_llm

    new_llm = _build_llm(arg)
    if new_llm is None:
        con.print(f"\n  [red]Failed to create model from '{arg}'.[/red]")
        con.print("  [dim]Format: provider:model (e.g. anthropic:claude-opus-4-20250514, openai:gpt-4o)[/dim]\n")
        return

    # Hot-swap on agent
    agent = getattr(state, "agent", None)
    if agent:
        agent.llm = new_llm

    # Hot-swap on orchestrator (for delegate_to_worker)
    orch = getattr(state, "orchestrator", None)
    if orch:
        orch.llm = new_llm

    con.print(f"\n  Model switched to [bold]{arg}[/bold]\n")


async def _chat_loop(
    llm_config: str, verbose: bool, mcp_url: Optional[str] = None
) -> None:
    """Event-driven interactive chat with parallel agents, /btw, and agent panel."""
    import signal

    from aki.agent.logger import set_verbose
    from aki.api.session_manager import get_session_manager
    from aki.cli.events import UIEvent, UIEventBus, UIEventType
    from aki.cli.focus import FocusManager
    from aki.cli.input import AsyncInputReader
    from aki.cli.renderer import RichRenderer

    set_verbose(verbose)

    # --- MCP tool discovery (same as before) ---
    extra_tools: list[Any] = []
    from aki.mcp.client.adapter import discover_all_configured_tools

    try:
        config_tools = await discover_all_configured_tools()
        if config_tools:
            extra_tools.extend(config_tools)
            names = [t.name for t in config_tools]
            console.print(f"[dim]MCP config: loaded {len(config_tools)} tools ({', '.join(names)})[/dim]")
    except Exception as exc:
        console.print(f"[dim yellow]MCP config load skipped: {exc}[/dim yellow]")

    if mcp_url:
        from aki.mcp.client.adapter import discover_mcp_base_tools

        console.print(f"[dim]Connecting to MCP server {mcp_url} ...[/dim]")
        mcp_tools = await discover_mcp_base_tools(url=mcp_url, server_name="adhoc")
        extra_tools.extend(mcp_tools)
        tool_names = [t.name for t in mcp_tools]
        console.print(f"[dim]MCP --mcp: loaded {len(mcp_tools)} tools ({', '.join(tool_names)})[/dim]")

    # --- Session setup ---
    manager = get_session_manager()
    state = await manager.create_session(
        user_id="cli-user",
        llm_config=llm_config,
        extra_tools=extra_tools or None,
        auto_load_mcp=False,
    )
    if verbose:
        console.print(f"[dim]Session {state.session_id[:8]}[/dim]")

    # --- Event-driven architecture ---
    event_bus = UIEventBus()
    dispatch_sub = event_bus.subscribe()  # dispatch loop's own subscriber
    input_reader = AsyncInputReader(event_bus)
    renderer = RichRenderer(event_bus, console)  # renderer subscribes internally
    focus = FocusManager(default_focus=state.agent.agent_id if state.agent else "orchestrator")

    # AgentCallback → UIEventBus bridge
    class _CallbackBridge:
        async def on_thinking(self, agent_id: str, iteration: int) -> None:
            event_bus.emit_nowait(UIEvent(
                type=UIEventType.AGENT_THINKING, agent_id=agent_id,
                data={"iteration": iteration},
            ))

        async def on_tool_start(self, agent_id: str, tool_name: str, params: dict) -> None:
            event_bus.emit_nowait(UIEvent(
                type=UIEventType.TOOL_START, agent_id=agent_id,
                data={"tool_name": tool_name, "params": params},
            ))

        async def on_tool_end(self, agent_id: str, tool_name: str, success: bool, duration_ms: float) -> None:
            event_bus.emit_nowait(UIEvent(
                type=UIEventType.TOOL_END, agent_id=agent_id,
                data={"tool_name": tool_name, "success": success, "duration_ms": duration_ms},
            ))

        async def on_reply(self, agent_id: str, content: str) -> None:
            event_bus.emit_nowait(UIEvent(
                type=UIEventType.AGENT_REPLY, agent_id=agent_id,
                data={"content": content},
            ))

    callback_bridge = _CallbackBridge()

    # Inject callback into agent and delegate_to_worker
    if state.agent:
        state.agent._callback = callback_bridge
        renderer._ensure_agent(state.agent.agent_id).is_focus = True
    if state.orchestrator:
        for t in state.orchestrator.tools:
            if t.name == "delegate_to_worker":
                t._callback = callback_bridge

    # Signal handling
    _cancel_count = 0

    def _sigint_handler(sig: int, frame: Any) -> None:
        nonlocal _cancel_count
        _cancel_count += 1
        if _cancel_count == 1:
            event_bus.emit_nowait(UIEvent(type=UIEventType.CANCEL, data={"scope": "current"}))
        else:
            event_bus.emit_nowait(UIEvent(type=UIEventType.CANCEL, data={"scope": "all"}))

    signal.signal(signal.SIGINT, _sigint_handler)

    # --- Agent turn runner ---
    agent_task: Optional[asyncio.Task] = None

    async def run_agent_turn(text: str) -> None:
        try:
            result = await manager.send_message(state.session_id, text)
            # The AgentCallback.on_reply() already emits AGENT_REPLY via the bus.
            # Only emit here as fallback if callback wasn't triggered (e.g. empty reply).
            reply = result.get("reply", "")
            if reply and not (state.agent and state.agent._callback):
                event_bus.emit_nowait(UIEvent(
                    type=UIEventType.AGENT_REPLY,
                    agent_id=state.agent.agent_id if state.agent else "",
                    data={"content": reply},
                ))
        except asyncio.CancelledError:
            console.print("\n[dim]Agent cancelled.[/dim]")
        except Exception as e:
            event_bus.emit_nowait(UIEvent(
                type=UIEventType.ERROR, data={"error": str(e)},
            ))

    async def handle_btw(message: str) -> None:
        """Side question — runs a separate agent to avoid race conditions."""
        if not state.agent:
            return
        try:
            # Create a lightweight one-shot agent with same llm but isolated state
            from aki.agent.base import UniversalAgent
            from aki.agent.state import AgentContext

            btw_agent = UniversalAgent(
                context=AgentContext(),
                llm=state.agent.llm,
                tools=state.agent.tools,
                agent_name="btw",
            )
            history_snapshot = list(state.conversation_history)
            reply = await btw_agent.run_turn(
                f"[Side question - answer briefly in 1-2 sentences]: {message}",
                history_snapshot,
            )
            event_bus.emit_nowait(UIEvent(
                type=UIEventType.BTW_REPLY,
                data={"reply": str(reply)},
            ))
        except Exception as e:
            event_bus.emit_nowait(UIEvent(
                type=UIEventType.ERROR, data={"error": f"btw failed: {e}"},
            ))

    # --- Dispatch loop ---
    async def dispatch_loop() -> None:
        nonlocal agent_task, _cancel_count
        while True:
            event = await dispatch_sub.next(timeout=0.1)
            if event is None:
                continue

            if event.type == UIEventType.USER_INPUT:
                text = event.data.get("text", "").strip()
                if not text:
                    continue

                # Strip any non-printable chars that may leak from terminal
                text = "".join(c for c in text if c.isprintable() or c in ("\n", "\t"))
                lower = text.strip().lower()

                # --- Slash commands (always processed, even when agent is busy) ---
                if lower in ("/quit", "/exit", "/q"):
                    input_reader.stop()
                    renderer.stop()
                    console.print("\n[dim]Bye.[/dim]")
                    break

                if lower in ("/help", "/?"):
                    console.print()
                    console.print("[dim]  /quit              Exit[/dim]")
                    console.print("[dim]  /persona [name]    List or switch persona[/dim]")
                    console.print("[dim]  /model [p:model]   Show or switch model (e.g. anthropic:claude-opus-4-20250514)[/dim]")
                    console.print("[dim]  /history           Show conversation history[/dim]")
                    console.print("[dim]  /status            Session info[/dim]")
                    console.print("[dim]  /agents            Show active agents[/dim]")
                    console.print("[dim]  /btw <msg>         Side question (won't interrupt current task)[/dim]")
                    console.print("[dim]  /focus <name>      Focus on specific agent[/dim]")
                    console.print("[dim]  /watch <name>      Watch agent events[/dim]")
                    console.print("[dim]  /unwatch           Stop watching[/dim]")
                    console.print("[dim]  /kill <name>       Cancel agent[/dim]")
                    console.print()
                    continue

                if lower.startswith("/persona"):
                    _handle_persona_command(text[8:].strip(), console)
                    continue

                if lower.startswith("/model"):
                    arg = text[6:].strip()
                    _handle_model_command(arg, state, console)
                    continue

                if lower.startswith("/btw"):
                    btw_body = text[4:].strip()
                    if btw_body:
                        asyncio.create_task(handle_btw(btw_body))
                    else:
                        console.print("[dim]Usage: /btw <message>[/dim]")
                    continue

                if lower == "/agents":
                    orch = getattr(state, "orchestrator", None)
                    if orch and hasattr(orch, "_task_registry"):
                        renderer.sync_from_task_registry(orch._task_registry)
                    renderer.show_agent_panel()
                    continue

                if lower == "/history":
                    history = manager.get_history(state.session_id)
                    if not history:
                        console.print("[dim]No messages yet.[/dim]")
                    else:
                        console.print()
                        for msg in history:
                            rl = msg.get("role", "?")
                            content = msg.get("content", "")
                            if rl == "user":
                                console.print(f"[bold]> {content}[/bold]")
                            else:
                                console.print(f"[dim]{content}[/dim]")
                            console.print()
                    continue

                if lower == "/status":
                    agent = state.agent
                    turn = agent._turn_count if agent else 0
                    console.print(
                        f"[dim]Session: {state.session_id[:8]}  "
                        f"Turns: {turn}  "
                        f"History: {len(state.conversation_history)} messages[/dim]"
                    )
                    continue

                if lower.startswith("/focus"):
                    target = text[6:].strip()
                    if target:
                        focus.switch_focus(target)
                        renderer.set_focus(target)
                        console.print(f"[dim]Focus switched to: {target}[/dim]")
                    else:
                        console.print(f"[dim]Current focus: {focus.current_focus}[/dim]")
                    continue

                if lower.startswith("/watch"):
                    target = text[6:].strip()
                    if target:
                        focus.start_watch(target)
                        renderer.set_watch(target)
                    else:
                        console.print("[dim]Usage: /watch <agent_name>[/dim]")
                    continue

                if lower == "/unwatch":
                    focus.stop_watch()
                    renderer.set_watch(None)
                    continue

                if lower.startswith("/kill"):
                    target = text[5:].strip()
                    if not target:
                        console.print("[dim]Usage: /kill <agent_name>[/dim]")
                        continue
                    orch = getattr(state, "orchestrator", None)
                    if orch and hasattr(orch, "_task_registry"):
                        if orch._task_registry.cancel(target):
                            console.print(f"[dim]Cancelled: {target}[/dim]")
                        else:
                            console.print(f"[dim]Not found or not running: {target}[/dim]")
                    continue

                # Normal message — send to agent
                if agent_task and not agent_task.done():
                    console.print("[dim]Agent is busy. Use /btw for side questions.[/dim]")
                    continue

                _cancel_count = 0
                agent_task = asyncio.create_task(run_agent_turn(text))

            elif event.type == UIEventType.CANCEL:
                scope = event.data.get("scope", "current")
                if scope == "current" and agent_task and not agent_task.done():
                    agent_task.cancel()
                elif scope == "all":
                    if agent_task and not agent_task.done():
                        agent_task.cancel()
                    input_reader.stop()
                    renderer.stop()
                    break

    # --- Run all three concurrent tasks ---
    try:
        await asyncio.gather(
            input_reader.run(),
            renderer.run(),
            dispatch_loop(),
            return_exceptions=True,
        )
    finally:
        manager.cleanup_session(state.session_id)


@app.command()
def gateway(
    discord_token: str = typer.Option("", "--discord-token", envvar="AKI_GATEWAY_DISCORD_TOKEN", help="Discord bot token"),
    discord_channels: str = typer.Option("", "--discord-channels", envvar="AKI_GATEWAY_DISCORD_CHANNEL_IDS", help="Comma-separated allowed channel IDs"),
    host: str = typer.Option("0.0.0.0", "--host", help="REST API bind host"),
    port: int = typer.Option(8080, "--port", help="REST API bind port"),
    disable_tools: str = typer.Option(
        "", "--disable-tools", envvar="AKI_DISABLE_TOOLS",
        help="Comma-separated tool names to disable (e.g. shell,system_restart)",
    ),
) -> None:
    """Start the gateway (Discord bot + REST API in one process)."""
    channels = [c.strip() for c in discord_channels.split(",") if c.strip()] or None
    disabled = [t.strip() for t in disable_tools.split(",") if t.strip()] or None

    # Check both CLI arg and settings for Discord token
    settings = get_settings()
    has_discord = bool(discord_token or settings.gateway.discord_token)

    info_lines = [f"[bold]Host:[/bold] {host}:{port}"]
    info_lines.append("[bold]Discord:[/bold] enabled" if has_discord else "[dim]Discord: not configured[/dim]")
    if disabled:
        info_lines.append(f"[bold]Disabled tools:[/bold] {', '.join(disabled)}")
    info_lines.append("[dim]Press Ctrl+C to stop.[/dim]")

    console.print(Panel("\n".join(info_lines), title="Aki Gateway", border_style="blue"))

    if os.environ.pop("AKI_RESTARTED", None):
        console.print("[green]Restarted successfully.[/green]")

    try:
        from aki.gateway import launch_gateway

        asyncio.run(launch_gateway(
            host=host,
            port=port,
            discord_token=discord_token or None,
            discord_channels=channels,
            disabled_tools=disabled,
        ))
    except KeyboardInterrupt:
        console.print("\n[dim]Gateway stopped.[/dim]")
    except Exception as e:
        console.print(f"[red]Gateway error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def subtitle(
    video: str = typer.Argument(..., help="Path to video file"),
    source_lang: str = typer.Option("en", "--source", "-s", help="Source language"),
    target_lang: str = typer.Option("zh", "--target", "-t", help="Target language"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output SRT filename"),
    enable_vision: bool = typer.Option(False, "--vision", help="Enable vision analysis"),
    quality: str = typer.Option(
        "balanced",
        "--quality",
        help="Quality profile: fast, balanced, high_quality",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
) -> None:
    """Generate subtitles for a video file."""
    console.print(
        Panel(
            f"[bold]Video:[/bold] {video}\n"
            f"[bold]Source:[/bold] {source_lang} → [bold]Target:[/bold] {target_lang}",
            title="Subtitle Generation",
            border_style="blue",
        )
    )

    if output and output.strip().startswith("-"):
        console.print(
            "[red]Error: --output/-o requires a filename, but received an option-like value.[/red]"
        )
        raise typer.Exit(2)

    try:
        result = asyncio.run(
            _run_subtitle_pipeline(
                video=video,
                source_lang=source_lang,
                target_lang=target_lang,
                enable_vision=enable_vision,
                output_name=output,
                quality_profile=quality,
                verbose=verbose,
            )
        )
        console.print("\n[bold green]Subtitles generated:[/bold green]")
        console.print(result["result"])
        console.print(f"\n[dim]Task ID: {result['task_id']}[/dim]")
        console.print(f"[dim]Task folder: {result['task_dir']}[/dim]")
        console.print(f"[dim]Template result: {result['template_path']}[/dim]")
        console.print(f"[dim]Translation result: {result['translation_path']}[/dim]")
        if result.get("proofread_path"):
            console.print(f"[dim]Proofread result: {result['proofread_path']}[/dim]")
        if result.get("edit_path"):
            console.print(f"[dim]Edit result: {result['edit_path']}[/dim]")
        if result.get("memory_path"):
            console.print(f"[dim]Memory snapshot: {result['memory_path']}[/dim]")
        console.print(f"[dim]Output saved to: {result['srt_path']}[/dim]")
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


@app.command()
def translate(
    text: str = typer.Argument(..., help="Text to translate"),
    target_lang: str = typer.Option("zh", "--target", "-t", help="Target language"),
    source_lang: str = typer.Option("auto", "--source", "-s", help="Source language"),
) -> None:
    """Translate text using the translation agent."""
    task = f"""Translate the following text:
Source language: {source_lang}
Target language: {target_lang}
Text: {text}"""

    try:
        result = asyncio.run(_run_task(task, "translation", verbose=False))
        console.print(result)
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


@app.command()
def tools() -> None:
    """List all available tools."""
    import asyncio
    from aki.tools import ToolRegistry

    console.print("[bold]Built-in Tools:[/bold]\n")

    for tool_name in ToolRegistry.list_tools():
        tool = ToolRegistry.get(tool_name)
        console.print(f"  [cyan]{tool.name}[/cyan]")
        console.print(f"    {tool.description}")
        console.print()

    async def _list_mcp() -> None:
        from aki.mcp.client.adapter import discover_all_configured_tools

        try:
            mcp_tools = await discover_all_configured_tools()
        except Exception as exc:
            console.print(f"[yellow]MCP tools unavailable: {exc}[/yellow]")
            return
        if not mcp_tools:
            return
        console.print("[bold]MCP Tools:[/bold]\n")
        for tool in mcp_tools:
            console.print(f"  [cyan]{tool.name}[/cyan]")
            console.print(f"    {tool.description}")
            console.print()

    asyncio.run(_list_mcp())


@app.command()
def agents() -> None:
    """List all available agents."""
    from aki.agent import AgentRegistry

    console.print("[bold]Available Agents:[/bold]\n")

    for agent_name in AgentRegistry.list_agents():
        agent_class = AgentRegistry.get_class(agent_name)
        console.print(f"  [cyan]{agent_class.name}[/cyan]")
        console.print(f"    {agent_class.description}")
        console.print()


def _parse_memory_categories(raw: Optional[str]) -> Optional[set[str]]:
    """Parse comma-separated category list."""
    if raw is None:
        return None
    values = {item.strip() for item in raw.split(",") if item.strip()}
    return values or None


@memory_app.command("stats")
def memory_stats() -> None:
    """Show memory statistics."""
    memory = _build_runtime_memory_manager()
    stats = asyncio.run(memory.get_stats())
    console.print("[bold]Memory Stats:[/bold]")
    for key, value in stats.items():
        console.print(f"  {key}: {value}")


@memory_app.command("list")
def memory_list(
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Search query"),
    limit: int = typer.Option(20, "--limit", "-n", min=1, help="Maximum results"),
    categories: Optional[str] = typer.Option(
        None,
        "--categories",
        "-c",
        help="Comma-separated categories (user_instruction,domain_knowledge,web_knowledge)",
    ),
    namespace: Optional[str] = typer.Option(None, "--namespace", help="Memory namespace"),
    include_expired: bool = typer.Option(
        False, "--include-expired", help="Include expired records"
    ),
) -> None:
    """List long-term memory records."""
    memory = _build_runtime_memory_manager()
    category_filter = _parse_memory_categories(categories)

    items = asyncio.run(
        memory.recall_long_term(
            query=query,
            limit=limit,
            categories=category_filter,
            namespace=namespace,
            include_expired=include_expired,
        )
    )
    console.print(f"[bold]Long-Term Memory ({len(items)} items)[/bold]")
    for idx, item in enumerate(items, start=1):
        source = f" | source={item.source_uri}" if item.source_uri else ""
        expiry = f" | expires={item.expires_at.isoformat()}" if item.expires_at else ""
        snippet = (
            item.content if len(item.content) <= 180 else item.content[:180] + "...<truncated>"
        )
        console.print(
            f"{idx}. [{item.category.value}] ns={item.namespace} imp={item.importance:.2f}{source}{expiry}"
        )
        console.print(f"   {snippet}")


@memory_app.command("prune")
def memory_prune() -> None:
    """Prune expired long-term memory records."""
    memory = _build_runtime_memory_manager()
    removed = asyncio.run(memory.prune_long_term())
    console.print(f"[green]Pruned {removed} expired long-term memories.[/green]")


@memory_app.command("upsert-instruction")
def memory_upsert_instruction(
    key: str = typer.Argument(..., help="Instruction key"),
    content: str = typer.Argument(..., help="Instruction content"),
    namespace: Optional[str] = typer.Option(None, "--namespace", help="Memory namespace"),
    source_uri: Optional[str] = typer.Option(None, "--source", help="Optional source URI"),
) -> None:
    """Upsert a user instruction into long-term memory."""
    memory = _build_runtime_memory_manager()
    item = asyncio.run(
        memory.upsert_user_instruction(
            key=key,
            content=content,
            namespace=namespace,
            source_uri=source_uri,
        )
    )
    console.print("[green]Stored user instruction.[/green]")
    console.print(f"  id: {item.id}")
    console.print(f"  namespace: {item.namespace}")
    console.print(f"  category: {item.category.value}")


@memory_app.command("migrate-legacy-json")
def memory_migrate_legacy_json(
    source_file: str = typer.Argument(..., help="Path to legacy JSON memory file"),
    namespace: Optional[str] = typer.Option(None, "--namespace", help="Target namespace"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview migration without writing"),
) -> None:
    """Migrate a legacy JSON memory file into long-term memory."""
    from aki.memory import migrate_legacy_json_to_long_term

    memory = _build_runtime_memory_manager()
    result = asyncio.run(
        migrate_legacy_json_to_long_term(
            memory_manager=memory,
            source_file=source_file,
            namespace=namespace,
            dry_run=dry_run,
        )
    )
    console.print("[bold]Migration Result:[/bold]")
    for key, value in result.items():
        console.print(f"  {key}: {value}")


@app.command("serve")
def serve(
    host: str = typer.Option("0.0.0.0", help="Host to bind to"),
    port: int = typer.Option(8080, help="Port to listen on"),
) -> None:
    """Run Aki as an HTTP API server for interactive agent sessions."""
    console.print(f"[bold blue]Starting Aki HTTP API Server on {host}:{port}...[/bold blue]")
    console.print("[dim]Endpoints: POST /api/v1/sessions, POST /api/v1/sessions/:id/messages[/dim]")

    from aki.api.server import run_server

    run_server(host=host, port=port)


@app.command("mcp-server")
def mcp_server() -> None:
    """Run Aki as an MCP server (stdio transport)."""
    from aki.mcp import check_mcp_status

    status = check_mcp_status()

    if not status["mcp_installed"]:
        console.print("[red]Error: MCP SDK not installed.[/red]")
        console.print("Install with: pip install mcp")
        raise typer.Exit(1)

    console.print("[bold blue]Starting Aki MCP Server...[/bold blue]")
    console.print("[dim]Using stdio transport. Connect from Claude Desktop or Cursor.[/dim]")

    from aki.mcp.server import run_mcp_server

    asyncio.run(run_mcp_server())


@app.command("mcp-status")
def mcp_status() -> None:
    """Check MCP SDK installation status."""
    from aki.mcp import check_mcp_status

    status = check_mcp_status()

    console.print("[bold]MCP Status:[/bold]")
    console.print(
        f"  SDK Installed: {'[green]Yes[/green]' if status['mcp_installed'] else '[red]No[/red]'}"
    )
    console.print(
        f"  Server Available: {'[green]Yes[/green]' if status['server_available'] else '[yellow]No[/yellow]'}"
    )
    console.print(
        f"  Client Available: {'[green]Yes[/green]' if status['client_available'] else '[yellow]No[/yellow]'}"
    )

    if not status["mcp_installed"]:
        console.print("\n[dim]Install MCP SDK with: pip install mcp[/dim]")


@app.command("mcp-call")
def mcp_call(
    url: str = typer.Option(..., "--url", "-u", help="MCP server URL (streamable HTTP)"),
    tool: str = typer.Option(None, "--tool", "-t", help="Tool name to call (omit to list tools)"),
    args: str = typer.Option("{}", "--args", "-a", help="Tool arguments as JSON string"),
    server_name: str = typer.Option("remote", "--name", "-n", help="Server name for display"),
) -> None:
    """Call tools on a remote MCP server (streamable HTTP).

    Examples:

        # List available tools
        aki mcp-call -u http://localhost:8001/mcp

        # Call a specific tool
        aki mcp-call -u http://localhost:8001/mcp -t get_recommendations -a '{"user_id":"abc","limit":5}'
    """
    from aki.mcp import check_mcp_status

    status = check_mcp_status()
    if not status["mcp_installed"]:
        console.print("[red]Error: MCP SDK not installed. Install with: pip install mcp[/red]")
        raise typer.Exit(1)

    from aki.mcp.client.client import MCPClient, MCPServerConfig

    config = MCPServerConfig(
        name=server_name,
        transport="streamable-http",
        url=url,
    )

    async def _run() -> None:
        client = MCPClient()
        async with client.connect(config) as session:
            tools = await client.list_tools(session, config.name)

            if tool is None:
                # List tools mode
                console.print(f"\n[bold blue]MCP Server:[/bold blue] {url}")
                console.print(f"[bold]Found {len(tools)} tools:[/bold]\n")
                for t in tools:
                    console.print(f"  [green]{t.name}[/green]")
                    if t.description:
                        console.print(f"    {t.description}")
                    if t.input_schema.get("properties"):
                        params = ", ".join(
                            f"{k}{'*' if k in t.input_schema.get('required', []) else ''}"
                            for k in t.input_schema["properties"]
                        )
                        console.print(f"    [dim]params: {params}[/dim]")
                    console.print()
            else:
                # Call tool mode
                parsed_args = json.loads(args)
                console.print(f"[bold blue]Calling[/bold blue] {tool}({json.dumps(parsed_args, ensure_ascii=False)})")
                result = await client.call_tool(session, tool, parsed_args)
                console.print("\n[bold green]Result:[/bold green]")
                # Try to pretty-print JSON
                try:
                    parsed = json.loads(str(result))
                    console.print_json(json.dumps(parsed, ensure_ascii=False))
                except (json.JSONDecodeError, TypeError):
                    console.print(str(result))

    asyncio.run(_run())


@app.callback()
def main() -> None:
    """Aki — an agentic system with personality and autonomy."""
    pass


if __name__ == "__main__":
    app()
