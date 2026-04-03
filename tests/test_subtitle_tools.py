"""Tests for subtitle tool migration path."""

import pytest

from aki.tools import ToolRegistry
from aki.tools.io.srt import SRTWriteTool
from aki.tools.subtitle.editor import SubtitleEditTool
from aki.tools.subtitle.proofreader import SubtitleProofreadTool
from aki.tools.subtitle.translator import SubtitleTranslateTool


class MockLLM:
    """Simple mock LLM that returns predefined contents in order."""

    def __init__(self, responses: list[str]):
        self._responses = responses
        self._idx = 0

    async def chat(self, messages, **kwargs):
        if self._idx >= len(self._responses):
            content = self._responses[-1] if self._responses else ""
        else:
            content = self._responses[self._idx]
            self._idx += 1

        class Response:
            model = "mock"
            usage = {}

            def __init__(self, text: str):
                self.content = text

        return Response(content)


def test_subtitle_tools_registered():
    """Subtitle tools should be registered in the global registry."""
    tool_names = set(ToolRegistry.list_tools())
    assert "subtitle_translate" in tool_names
    assert "subtitle_proofread" in tool_names
    assert "subtitle_edit" in tool_names


@pytest.mark.asyncio
async def test_srt_write_prefer_translation(tmp_path):
    """SRT writer should output translation when prefer_translation=True."""
    out_path = tmp_path / "out.srt"
    tool = SRTWriteTool()
    result = await tool(
        file_path=str(out_path),
        subtitles=[
            {
                "index": 1,
                "start_time": "00:00:00,000",
                "end_time": "00:00:01,000",
                "text": "Hello",
                "translation": "你好",
            }
        ],
        prefer_translation=True,
    )

    assert result.success
    content = out_path.read_text(encoding="utf-8")
    assert "你好" in content
    assert "Hello" not in content


@pytest.mark.asyncio
async def test_subtitle_translate_tool_basic_flow():
    """Translator should set src_text and translation fields."""
    tool = SubtitleTranslateTool(llm_model=MockLLM(["第一行", "第二行"]))
    result = await tool(
        subtitles=[
            {
                "index": 1,
                "start_time": "00:00:00,000",
                "end_time": "00:00:01,000",
                "text": "Line one",
            },
            {
                "index": 2,
                "start_time": "00:00:01,000",
                "end_time": "00:00:02,000",
                "text": "Line two",
            },
        ],
        source_language="en",
        target_language="zh",
        split_threshold=9999,
    )

    assert result.success
    subtitles = result.data["subtitles"]
    assert subtitles[0]["src_text"] == "Line one"
    assert subtitles[0]["translation"] == "第一行"
    assert subtitles[1]["translation"] == "第二行"


@pytest.mark.asyncio
async def test_subtitle_proofread_and_edit_tools():
    """Proofreader should suggest changes, editor should apply final text updates."""
    proof_tool = SubtitleProofreadTool(
        llm_model=MockLLM(
            [
                (
                    '{"suggestions":[{"id":1,"suggestion":"修正后第一行",'
                    '"issue_type":"fluency","severity":"medium","rationale":"更自然"}]}'
                )
            ]
        )
    )
    proof_result = await proof_tool(
        subtitles=[
            {
                "index": 1,
                "start_time": "00:00:00,000",
                "end_time": "00:00:01,000",
                "text": "Line one",
                "src_text": "Line one",
                "translation": "第一行",
            }
        ],
        target_language="zh",
        batch_size=1,
    )
    assert proof_result.success
    proved = proof_result.data["subtitles"]
    suggestions = proof_result.data["suggestions"]
    assert proved[0]["translation"] == "第一行"
    assert suggestions[0]["suggestion"] == "修正后第一行"
    assert suggestions[0]["issue_type"] == "fluency"

    edit_tool = SubtitleEditTool(llm_model=MockLLM(["最终第一行"]))
    edit_result = await edit_tool(
        subtitles=proved,
        domain="general",
        context_window=1,
        suggestions=suggestions,
    )
    assert edit_result.success
    edited = edit_result.data["subtitles"]
    assert edited[0]["translation"] == "最终第一行"
