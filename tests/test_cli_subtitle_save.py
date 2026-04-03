"""CLI subtitle command output persistence tests."""

from pathlib import Path

from typer.testing import CliRunner

from aki.cli.main import app

runner = CliRunner()

def test_subtitle_saves_to_explicit_output(monkeypatch, tmp_path):
    """subtitle command should save result under outputs/<task_id>/requested_name."""

    async def _fake_pipeline(
        video,
        source_lang,
        target_lang,
        enable_vision,
        output_name,
        quality_profile,
        verbose,
    ):
        del video, source_lang, target_lang, enable_vision, output_name, quality_profile, verbose
        task_dir = tmp_path / "outputs" / "Translate_demo_20260101_000000"
        task_dir.mkdir(parents=True, exist_ok=True)
        srt_path = task_dir / "custom_output.srt"
        srt_path.write_text(
            "1\n00:00:00,000 --> 00:00:02,000\n你好，世界\n",
            encoding="utf-8",
        )
        template_path = task_dir / "subtitle_template.json"
        template_path.write_text("{}", encoding="utf-8")
        translation_path = task_dir / "subtitle_translation_result.json"
        translation_path.write_text("{}", encoding="utf-8")
        return {
            "task_id": "Translate demo",
            "task_dir": str(task_dir),
            "template_path": str(template_path),
            "translation_path": str(translation_path),
            "srt_path": str(srt_path),
            "result": {"subtitles": [{"translation": "你好，世界"}], "count": 1},
        }

    monkeypatch.setattr("aki.cli.main._run_subtitle_pipeline", _fake_pipeline)

    video_path = tmp_path / "demo.mp4"

    result = runner.invoke(
        app,
        ["subtitle", str(video_path), "--source", "en", "--target", "zh", "--output", "custom_output.srt"],
    )

    assert result.exit_code == 0
    assert "Output saved to:" in result.output
    assert "Task folder:" in result.output


def test_subtitle_saves_to_default_output_when_not_provided(monkeypatch, tmp_path):
    """subtitle command should report auto-generated output path from pipeline."""

    async def _fake_pipeline(
        video,
        source_lang,
        target_lang,
        enable_vision,
        output_name,
        quality_profile,
        verbose,
    ):
        del video, source_lang, target_lang, enable_vision, output_name, quality_profile, verbose
        task_dir = tmp_path / "outputs" / "Translate_demo_video_20260101_000001"
        task_dir.mkdir(parents=True, exist_ok=True)
        srt_path = task_dir / "demo_video.zh.srt"
        srt_path.write_text(
            "1\n00:00:00,000 --> 00:00:02,000\n你好，世界\n",
            encoding="utf-8",
        )
        template_path = task_dir / "subtitle_template.json"
        template_path.write_text("{}", encoding="utf-8")
        translation_path = task_dir / "subtitle_translation_result.json"
        translation_path.write_text("{}", encoding="utf-8")
        return {
            "task_id": "Translate demo_video",
            "task_dir": str(task_dir),
            "template_path": str(template_path),
            "translation_path": str(translation_path),
            "srt_path": str(srt_path),
            "result": {"subtitles": [{"translation": "你好，世界"}], "count": 1},
        }

    monkeypatch.setattr("aki.cli.main._run_subtitle_pipeline", _fake_pipeline)

    video_path = tmp_path / "demo_video.mp4"

    result = runner.invoke(
        app,
        ["subtitle", str(video_path), "--source", "en", "--target", "zh"],
    )

    assert result.exit_code == 0
    assert "demo_video.zh.srt" in result.output


def test_subtitle_rejects_option_like_output_value(tmp_path):
    """subtitle should fail fast when -o is followed by another option token."""
    video_path = tmp_path / "demo.mp4"
    result = runner.invoke(app, ["subtitle", str(video_path), "--output", "-v"])
    assert result.exit_code == 2
    assert "requires a filename" in result.output
