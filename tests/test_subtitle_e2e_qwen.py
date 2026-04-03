"""End-to-end subtitle flow tests for Qwen ASR fallback behavior."""

import sys
import types

import pytest

from aki.agent import AgentOrchestrator, OrchestratorConfig
from aki.config import reset_settings
import aki.tools.audio.transcribe as transcribe_module
from aki.tools.audio.transcribe import TranscribeTool


class _ScriptedLLM:
    """Deterministic LLM stub for orchestrator integration tests."""

    def __init__(self, responses: list[str]):
        self._responses = responses
        self._calls = 0

    async def chat(self, messages, **kwargs):
        content = self._responses[self._calls]
        self._calls += 1

        class _Resp:
            model = "mock-llm"
            usage = {}

        resp = _Resp()
        resp.content = content
        return resp


class _FakeDashScopeResponse:
    """Minimal DashScope response payload."""

    status_code = 200
    usage = {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}
    output = {
        "choices": [
            {"message": {"content": [{"text": "hello from qwen asr"}]}},
        ]
    }


@pytest.mark.asyncio
async def test_subtitle_task_e2e_retries_dashscope_endpoint(monkeypatch, tmp_path):
    """Main-agent subtitle task should recover from default-endpoint auth mismatch."""
    reset_settings()
    monkeypatch.setenv("AKI_DASHSCOPE_API_KEY", "dashscope-key")
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("AKI_DASHSCOPE_BASE_URL", raising=False)
    monkeypatch.delenv("DASHSCOPE_BASE_URL", raising=False)
    monkeypatch.delenv("DASHSCOPE_BASE_HTTP_API_URL", raising=False)
    monkeypatch.setattr(
        transcribe_module, "_prepare_audio_input", lambda audio_path, provider: (audio_path, None)
    )
    monkeypatch.setattr(
        transcribe_module,
        "_split_audio_into_chunks",
        lambda audio_path, chunk_seconds=8: ([audio_path], None),
    )

    attempts: list[tuple[str | None, str]] = []

    class _FakeMMC:
        @staticmethod
        def call(**kwargs):
            base_url = getattr(fake_dashscope_module, "base_http_api_url", None)
            model = kwargs["model"]
            attempts.append((base_url, model))
            if base_url == "https://dashscope-intl.aliyuncs.com/api/v1":
                return _FakeDashScopeResponse()
            raise RuntimeError("InvalidApiKey: key belongs to an international endpoint")

    fake_dashscope_module = types.SimpleNamespace(MultiModalConversation=_FakeMMC)
    monkeypatch.setitem(sys.modules, "dashscope", fake_dashscope_module)

    media_file = tmp_path / "XIAOMI.mp4"
    media_file.write_bytes(b"RIFFxxxxWAVEfmt ")

    llm = _ScriptedLLM(
        responses=[
            (
                '{"type":"invoke_tool","target":"transcribe","params":'
                f'{{"audio_path":"{media_file}","language":"en","provider":"qwen","model":"qwen3-asr-flash"}}'
                ',"reasoning":"transcribe first"}'
            ),
            "COMPLETE",
        ]
    )

    from aki.agent.base import UniversalAgent
    from aki.agent.roles import Role
    from aki.agent.state import AgentContext

    test_role = Role(
        name="test_worker",
        persona="You are a test agent.",
        system_prompt="Execute tools exactly.",
        allowed_tools=["transcribe"],
    )

    agent = UniversalAgent(
        role=test_role,
        context=AgentContext(task_id="test", workspace_dir=str(tmp_path)),
        llm=llm,
        tools=[TranscribeTool()],
    )

    result = await agent.run(
        f"Generate subtitles for video: {media_file}\nSource language: en\nTarget language: zh"
    )

    assert result == "COMPLETE"
    assert attempts[0][0] is None
    assert any(base == "https://dashscope-intl.aliyuncs.com/api/v1" for base, _ in attempts)
