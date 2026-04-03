"""Tests for deterministic subtitle CLI pipeline."""

from pathlib import Path

import pytest

from aki.cli.main import (
    _build_template_subtitles,
    _build_template_subtitles_from_segments,
    _run_subtitle_pipeline,
)
from aki.tools.base import ToolResult


def test_build_template_subtitles_spans_full_duration():
    """Template subtitles should cover from 0 to full media duration."""
    subtitles = _build_template_subtitles(
        "Sentence one. Sentence two. Sentence three. Sentence four.",
        duration_seconds=40.0,
    )

    assert len(subtitles) >= 4
    assert subtitles[0]["start_time"] == "00:00:00,000"
    assert subtitles[-1]["end_time"] == "00:00:40,000"
    for sub in subtitles:
        assert sub["start_time"] < sub["end_time"]


def test_build_template_subtitles_from_segments_uses_asr_timing():
    """Segment-derived template should preserve source timing boundaries."""
    subtitles = _build_template_subtitles_from_segments(
        [
            {"start_seconds": 0.0, "end_seconds": 3.1, "text": "Hello"},
            {"start_seconds": 3.1, "end_seconds": 7.4, "text": "World"},
        ]
    )
    assert len(subtitles) == 2
    assert subtitles[0]["start_time"] == "00:00:00,000"
    assert subtitles[0]["end_time"] == "00:00:03,100"
    assert subtitles[1]["start_time"] == "00:00:03,100"
    assert subtitles[1]["end_time"] == "00:00:07,400"


@pytest.mark.asyncio
async def test_run_subtitle_pipeline_writes_outputs_folder(monkeypatch, tmp_path):
    """Pipeline should write template/translation/final files into outputs/<task_id>."""

    monkeypatch.chdir(tmp_path)

    class _Settings:
        default_audio = "qwen:qwen3-asr-flash"

    monkeypatch.setattr("aki.cli.main.get_settings", lambda: _Settings())
    monkeypatch.setattr("aki.cli.main._probe_media_duration_seconds", lambda media_path: 24.0)

    class _AudioExtractTool:
        async def __call__(self, **kwargs):
            del kwargs
            return ToolResult.ok(data={"audio_path": "demo.asr.mp3", "skipped": False})

    class _TranscribeTool:
        async def __call__(self, **kwargs):
            del kwargs
            return ToolResult.ok(
                data={
                    "text": "First sentence. Second sentence. Third sentence.",
                    "segments": [
                        {
                            "start_time": "00:00:00,000",
                            "end_time": "00:00:05,000",
                            "text": "First sentence.",
                        },
                        {
                            "start_time": "00:00:05,000",
                            "end_time": "00:00:10,000",
                            "text": "Second sentence.",
                        },
                    ],
                    "language": "en",
                    "chunked_audio": [
                        {
                            "index": 1,
                            "audio_path": "chunk_0001.mp3",
                            "start_seconds": 0.0,
                            "end_seconds": 5.0,
                        }
                    ],
                }
            )

    class _AudioVADTool:
        async def __call__(self, **kwargs):
            del kwargs
            return ToolResult.ok(
                data={
                    "audio_path": "demo.asr.mp3",
                    "chunk_dir": "audio_chunks",
                    "chunks": [
                        {
                            "index": 1,
                            "audio_path": "chunk_0001.mp3",
                            "start_seconds": 0.0,
                            "end_seconds": 5.0,
                            "start_time": "00:00:00,000",
                            "end_time": "00:00:05,000",
                        }
                    ],
                    "count": 1,
                    "duration_seconds": 24.0,
                }
            )

    class _SubtitleTranslateTool:
        async def __call__(self, subtitles, **kwargs):
            del kwargs
            translated = []
            for sub in subtitles:
                entry = dict(sub)
                entry["translation"] = f"ZH: {entry.get('text', '')}"
                translated.append(entry)
            return ToolResult.ok(data={"subtitles": translated, "count": len(translated)})

    class _SubtitleProofreadTool:
        async def __call__(self, subtitles, **kwargs):
            del kwargs
            return ToolResult.ok(
                data={
                    "subtitles": subtitles,
                    "count": len(subtitles),
                    "suggestions": [
                        {
                            "id": 1,
                            "suggestion": "ZH: First sentence (refined)",
                            "issue_type": "fluency",
                            "severity": "medium",
                            "rationale": "Use a more natural phrasing.",
                        }
                    ],
                    "suggestion_count": 1,
                }
            )

    class _SubtitleEditTool:
        async def __call__(self, subtitles, suggestions=None, **kwargs):
            del kwargs
            edited = [dict(item) for item in subtitles]
            if edited and suggestions:
                edited[0]["translation"] = suggestions[0]["suggestion"]
            return ToolResult.ok(
                data={
                    "subtitles": edited,
                    "count": len(edited),
                    "applied_suggestions": len(suggestions or []),
                }
            )

    class _SrtWriteTool:
        async def __call__(self, file_path, subtitles, prefer_translation=False, **kwargs):
            del kwargs
            output_path = Path(file_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            lines = []
            for i, sub in enumerate(subtitles, 1):
                text = sub.get("translation") if prefer_translation else sub.get("text")
                lines.extend(
                    [
                        str(i),
                        f"{sub.get('start_time')} --> {sub.get('end_time')}",
                        str(text or ""),
                        "",
                    ]
                )
            output_path.write_text("\n".join(lines), encoding="utf-8")
            return ToolResult.ok(data={"file_path": str(output_path), "count": len(subtitles)})

    def _fake_tool_get(name):
        tool_map = {
            "audio_extract": _AudioExtractTool(),
            "audio_vad": _AudioVADTool(),
            "transcribe": _TranscribeTool(),
            "subtitle_translate": _SubtitleTranslateTool(),
            "subtitle_proofread": _SubtitleProofreadTool(),
            "subtitle_edit": _SubtitleEditTool(),
            "srt_write": _SrtWriteTool(),
        }
        if name not in tool_map:
            raise AssertionError(f"Unexpected tool requested: {name}")
        return tool_map[name]

    monkeypatch.setattr("aki.tools.registry.ToolRegistry.get", _fake_tool_get)

    result = await _run_subtitle_pipeline(
        video="demo.mp4",
        source_lang="en",
        target_lang="zh",
        enable_vision=False,
        output_name="final.srt",
    )

    task_dir = Path(result["task_dir"])
    assert task_dir.parent.name == "outputs"
    assert task_dir.name.startswith("Translate_demo_")
    assert (task_dir / "task_meta.json").exists()
    assert (task_dir / "audio_vad_result.json").exists()
    assert (task_dir / "transcribe_result.json").exists()
    assert (task_dir / "subtitle_template.json").exists()
    assert (task_dir / "subtitle_translation_result.json").exists()
    assert (task_dir / "subtitle_proofread_result.json").exists()
    assert (task_dir / "subtitle_edit_result.json").exists()
    assert (task_dir / "memory_snapshot.json").exists()
    assert (task_dir / "transcript.txt").exists()
    assert Path(result["srt_path"]).exists()
    assert Path(result["srt_path"]).name == "final.srt"
    template_payload = (task_dir / "subtitle_template.json").read_text(encoding="utf-8")
    assert '"count": 2' in template_payload
    assert result["result"]["quality_profile"] == "balanced"
    assert result["result"]["review_suggestions"]
