"""Tests for DashScope-based Qwen audio integration."""

import sys
import types

import pytest

from aki.config import reset_settings
from aki.models import ModelConfig
from aki.models.providers.qwen import QwenAudio
from aki.tools import ToolRegistry
from aki.tools.audio.transcribe import TranscribeTool, _get_default_audio_config


class _FakeDashScopeResponse:
    """Minimal DashScope response stub."""

    def __init__(self):
        self.status_code = 200
        self.output = {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"text": "hello from qwen asr"},
                        ]
                    }
                }
            ]
        }
        self.usage = {
            "input_tokens": 10,
            "output_tokens": 2,
            "total_tokens": 12,
        }


@pytest.mark.asyncio
async def test_qwen_audio_transcribe_uses_dashscope(monkeypatch, tmp_path):
    """QwenAudio should call DashScope MultiModalConversation API."""
    captured = {}

    class _FakeMMC:
        @staticmethod
        def call(**kwargs):
            captured.update(kwargs)
            return _FakeDashScopeResponse()

    fake_dashscope_module = types.SimpleNamespace(MultiModalConversation=_FakeMMC)
    monkeypatch.setitem(sys.modules, "dashscope", fake_dashscope_module)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)

    sample_audio = tmp_path / "sample.wav"
    sample_audio.write_bytes(b"RIFFxxxxWAVEfmt ")

    model = QwenAudio(
        ModelConfig(
            provider="qwen",
            model_name="qwen3-asr-flash",
            api_key="dashscope-key",
        )
    )
    result = await model.transcribe(
        audio=str(sample_audio),
        language="EN",
        prompt="transcribe carefully",
    )

    assert result.content == "hello from qwen asr"
    assert result.model == "qwen3-asr-flash"
    assert result.usage == {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}
    assert captured["api_key"] == "dashscope-key"
    assert captured["model"] == "qwen3-asr-flash"
    assert captured["asr_options"]["language"] == "en"
    assert captured["messages"][0]["role"] == "system"
    assert captured["messages"][1]["role"] == "user"
    assert captured["messages"][1]["content"][0]["audio"].startswith("file://")


@pytest.mark.asyncio
async def test_qwen_audio_prefers_config_key_over_dashscope_env(monkeypatch, tmp_path):
    """Configured key should win over ambient DASHSCOPE_API_KEY."""
    captured = {}

    class _FakeMMC:
        @staticmethod
        def call(**kwargs):
            captured.update(kwargs)
            return _FakeDashScopeResponse()

    fake_dashscope_module = types.SimpleNamespace(MultiModalConversation=_FakeMMC)
    monkeypatch.setitem(sys.modules, "dashscope", fake_dashscope_module)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-env-key")

    sample_audio = tmp_path / "sample.wav"
    sample_audio.write_bytes(b"RIFFxxxxWAVEfmt ")

    model = QwenAudio(
        ModelConfig(
            provider="qwen",
            model_name="qwen3-asr-flash",
            api_key="config-key-should-win",
        )
    )
    await model.transcribe(audio=str(sample_audio), language="en")

    assert captured["api_key"] == "config-key-should-win"
    assert captured["messages"][0] == {"role": "system", "content": [{"text": ""}]}


@pytest.mark.asyncio
async def test_qwen_audio_falls_back_to_env_key_if_config_key_missing(monkeypatch, tmp_path):
    """DASHSCOPE_API_KEY should be used when model config key is empty."""
    captured = {}

    class _FakeMMC:
        @staticmethod
        def call(**kwargs):
            captured.update(kwargs)
            return _FakeDashScopeResponse()

    fake_dashscope_module = types.SimpleNamespace(MultiModalConversation=_FakeMMC)
    monkeypatch.setitem(sys.modules, "dashscope", fake_dashscope_module)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-env-key")

    sample_audio = tmp_path / "sample.wav"
    sample_audio.write_bytes(b"RIFFxxxxWAVEfmt ")

    model = QwenAudio(
        ModelConfig(
            provider="qwen",
            model_name="qwen3-asr-flash",
            api_key=None,
        )
    )
    await model.transcribe(audio=str(sample_audio), language="en")

    assert captured["api_key"] == "dashscope-env-key"


@pytest.mark.asyncio
async def test_qwen_audio_transcribe_normalizes_prefixed_model_name(monkeypatch, tmp_path):
    """model='qwen:...' should be normalized to DashScope model name."""
    captured = {}

    class _FakeMMC:
        @staticmethod
        def call(**kwargs):
            captured.update(kwargs)
            return _FakeDashScopeResponse()

    fake_dashscope_module = types.SimpleNamespace(MultiModalConversation=_FakeMMC)
    monkeypatch.setitem(sys.modules, "dashscope", fake_dashscope_module)

    sample_audio = tmp_path / "sample.wav"
    sample_audio.write_bytes(b"RIFFxxxxWAVEfmt ")

    model = QwenAudio(
        ModelConfig(
            provider="qwen",
            model_name="qwen:qwen3-asr-flash",
            api_key="dashscope-key",
        )
    )
    await model.transcribe(audio=str(sample_audio), language="en")

    assert captured["model"] == "qwen3-asr-flash"


@pytest.mark.asyncio
async def test_qwen_audio_transcribe_uses_us_endpoint_model_suffix(monkeypatch, tmp_path):
    """US endpoint should map qwen3-asr-flash to qwen3-asr-flash-us."""
    captured = {}

    class _FakeMMC:
        @staticmethod
        def call(**kwargs):
            captured.update(kwargs)
            return _FakeDashScopeResponse()

    fake_dashscope_module = types.SimpleNamespace(MultiModalConversation=_FakeMMC)
    monkeypatch.setitem(sys.modules, "dashscope", fake_dashscope_module)
    monkeypatch.setenv("AKI_DASHSCOPE_BASE_URL", "https://dashscope-us.aliyuncs.com/api/v1")

    sample_audio = tmp_path / "sample.wav"
    sample_audio.write_bytes(b"RIFFxxxxWAVEfmt ")

    model = QwenAudio(
        ModelConfig(
            provider="qwen",
            model_name="qwen3-asr-flash",
            api_key="dashscope-key",
        )
    )
    await model.transcribe(audio=str(sample_audio), language="en")

    assert captured["model"] == "qwen3-asr-flash-us"
    assert (
        getattr(fake_dashscope_module, "base_http_api_url", "")
        == "https://dashscope-us.aliyuncs.com/api/v1"
    )


@pytest.mark.asyncio
async def test_qwen_audio_retries_with_intl_endpoint_when_default_auth_fails(monkeypatch, tmp_path):
    """Auth failures on default endpoint should retry with intl endpoint."""
    attempts = []

    class _FakeMMC:
        @staticmethod
        def call(**kwargs):
            base_url = getattr(fake_dashscope_module, "base_http_api_url", None)
            attempts.append((base_url, kwargs.get("model")))
            if base_url == "https://dashscope-intl.aliyuncs.com/api/v1":
                return _FakeDashScopeResponse()
            raise RuntimeError("InvalidApiKey: key belongs to an international endpoint")

    fake_dashscope_module = types.SimpleNamespace(MultiModalConversation=_FakeMMC)
    monkeypatch.setitem(sys.modules, "dashscope", fake_dashscope_module)
    monkeypatch.delenv("AKI_DASHSCOPE_BASE_URL", raising=False)
    monkeypatch.delenv("DASHSCOPE_BASE_URL", raising=False)
    monkeypatch.delenv("DASHSCOPE_BASE_HTTP_API_URL", raising=False)

    sample_audio = tmp_path / "sample.wav"
    sample_audio.write_bytes(b"RIFFxxxxWAVEfmt ")

    model = QwenAudio(
        ModelConfig(
            provider="qwen",
            model_name="qwen3-asr-flash",
            api_key="dashscope-key",
        )
    )
    result = await model.transcribe(audio=str(sample_audio), language="en")

    assert result.content == "hello from qwen asr"
    assert attempts[0][0] is None
    assert any(base_url == "https://dashscope-intl.aliyuncs.com/api/v1" for base_url, _ in attempts)


@pytest.mark.asyncio
async def test_qwen_audio_retries_transient_transport_errors(monkeypatch, tmp_path):
    """Transient transport errors should be retried before failing."""
    call_count = {"value": 0}

    class _FakeMMC:
        @staticmethod
        def call(**kwargs):
            del kwargs
            call_count["value"] += 1
            if call_count["value"] < 3:
                raise RuntimeError(
                    "HTTPSConnectionPool(...): Max retries exceeded with url "
                    "(Caused by SSLError(SSLEOFError(8, '[SSL: UNEXPECTED_EOF_WHILE_READING]')))"
                )
            return _FakeDashScopeResponse()

    fake_dashscope_module = types.SimpleNamespace(MultiModalConversation=_FakeMMC)
    monkeypatch.setitem(sys.modules, "dashscope", fake_dashscope_module)

    sample_audio = tmp_path / "sample.wav"
    sample_audio.write_bytes(b"RIFFxxxxWAVEfmt ")

    model = QwenAudio(
        ModelConfig(
            provider="qwen",
            model_name="qwen3-asr-flash",
            api_key="dashscope-key",
        )
    )
    result = await model.transcribe(audio=str(sample_audio), language="en")

    assert result.content == "hello from qwen asr"
    assert call_count["value"] == 3


def test_default_audio_config_uses_dashscope_key_for_qwen(monkeypatch):
    """Audio tool default config should map qwen provider to DashScope key."""
    monkeypatch.setenv("AKI_DEFAULT_AUDIO", "qwen:qwen3-asr-flash")
    monkeypatch.setenv("AKI_DASHSCOPE_API_KEY", "dashscope-from-env")
    reset_settings()

    config = _get_default_audio_config()
    assert config.provider == "qwen"
    assert config.model_name == "qwen3-asr-flash"
    assert config.api_key == "dashscope-from-env"


def test_transcribe_tool_name_and_default_provider():
    """Tool should be renamed to transcribe and default provider should be qwen."""
    tool = ToolRegistry.get("transcribe")

    assert tool.name == "transcribe"
    provider_param = next(p for p in tool.parameters if p.name == "provider")
    assert provider_param.name == "provider"
    assert "whisper_transcribe" not in ToolRegistry.list_tools()


@pytest.mark.asyncio
async def test_transcribe_tool_maps_invalid_api_error_message():
    """InvalidApiKey errors should return actionable DashScope guidance."""

    class FailingAudioModel:
        async def transcribe(self, **kwargs):
            raise RuntimeError("InvalidApiKey: bad key")

    tool = TranscribeTool(
        audio_model=FailingAudioModel(),
        model_config=ModelConfig(provider="qwen", model_name="qwen3-asr-flash"),
    )
    result = await tool(audio_path="dummy.wav")

    assert not result.success
    assert "DashScope API key invalid" in (result.error or "")


@pytest.mark.asyncio
async def test_transcribe_accepts_provider_model_compact_syntax():
    """provider='qwen:model' should be parsed and used as model override."""

    class EchoAudioModel:
        async def transcribe(self, **kwargs):
            class Response:
                content = "ok"
                model = "qwen3-asr-flash"
                metadata = {"segments": [], "language": "en", "duration": None}

            return Response()

    tool = TranscribeTool(
        audio_model=EchoAudioModel(),
        model_config=ModelConfig(provider="qwen", model_name="qwen3-asr-flash"),
    )
    result = await tool(
        audio_path="dummy.wav",
        language="en",
        provider="qwen:qwen3-asr-flash",
    )

    assert result.success
    assert result.data["text"] == "ok"


@pytest.mark.asyncio
async def test_transcribe_accepts_model_compact_syntax():
    """model='qwen:model' should be normalized when provider is explicit."""

    class EchoAudioModel:
        async def transcribe(self, **kwargs):
            class Response:
                content = "ok"
                model = "qwen3-asr-flash"
                metadata = {"segments": [], "language": "en", "duration": None}

            return Response()

    tool = TranscribeTool(
        audio_model=EchoAudioModel(),
        model_config=ModelConfig(provider="qwen", model_name="qwen3-asr-flash"),
    )
    result = await tool(
        audio_path="dummy.wav",
        language="en",
        provider="qwen",
        model="qwen:qwen3-asr-flash",
    )

    assert result.success
    assert result.data["text"] == "ok"
