"""
OpenAI Provider Implementation

Supports GPT-4, GPT-4V, Whisper, and text-embedding models.
GPT-4o and later models support native web search via web_search_preview.
"""

import base64
import logging
from pathlib import Path
from typing import Any, AsyncIterator, Optional, Union

import json

from aki.models.base import ModelConfig, ModelResponse, ModelType, ToolCall
from aki.models.registry import ModelRegistry
from aki.models.types.audio import AudioModelInterface
from aki.models.types.embedding import EmbeddingModelInterface
from aki.models.types.llm import LLMInterface
from aki.models.types.vlm import VLMInterface


def _convert_image_blocks(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Anthropic-style image content blocks to OpenAI format.

    Anthropic: {"type": "image", "source": {"type": "url", "url": "..."}}
    OpenAI:    {"type": "image_url", "image_url": {"url": "..."}}

    Passes through messages without image blocks unchanged.
    """
    result = []
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            result.append(msg)
            continue
        # Convert content blocks
        converted_blocks = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "image":
                source = block.get("source", {})
                url = source.get("url", "")
                converted_blocks.append({
                    "type": "image_url",
                    "image_url": {"url": url},
                })
            else:
                converted_blocks.append(block)
        result.append({**msg, "content": converted_blocks})
    return result

logger = logging.getLogger(__name__)

# Models that support OpenAI's web_search_preview tool
_WEB_SEARCH_MODELS = {"gpt-4o", "gpt-4o-mini", "gpt-4.1", "o3", "o4-mini"}


def _model_supports_web_search(model_name: str) -> bool:
    return any(model_name.startswith(prefix) for prefix in _WEB_SEARCH_MODELS)


@ModelRegistry.register("openai", ModelType.LLM)
class OpenAILLM(LLMInterface):
    """OpenAI LLM implementation with native web search."""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self._client = None
        self.web_search_enabled: bool = True

    def _get_client(self):
        """Lazy initialization of OpenAI client."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError:
                raise ImportError("openai package required. Install with: pip install openai")

            self._client = AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
            )
        return self._client

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> ModelResponse:
        """Chat completion using OpenAI API with optional native web search."""
        client = self._get_client()

        # Convert image content blocks from Anthropic format to OpenAI format
        converted_messages = _convert_image_blocks(messages)

        request_params: dict[str, Any] = {
            "model": self.config.model_name,
            "messages": converted_messages,
            "temperature": temperature,
        }

        if max_tokens:
            request_params["max_tokens"] = max_tokens

        # Build tools list
        all_tools: list[dict[str, Any]] = list(tools or [])

        # Inject server-side web search for supported models
        if (
            self.web_search_enabled
            and _model_supports_web_search(self.config.model_name)
            and not self.config.base_url  # only for official OpenAI API
        ):
            # Remove Tavily web_search/web_read_page — server-side search supersedes them
            all_tools = [
                t for t in all_tools
                if not (t.get("type") == "function" and t.get("function", {}).get("name") in ("web_search", "web_read_page"))
            ]
            all_tools.append({"type": "web_search_preview"})

        if all_tools:
            request_params["tools"] = all_tools

        request_params.update(kwargs)

        response = await client.chat.completions.create(**request_params)

        # Extract content and tool calls
        message = response.choices[0].message
        content: Any = message.content or ""
        tool_calls: list[ToolCall] = []

        if message.tool_calls:
            for tc in message.tool_calls:
                # Skip server-side tool calls (web search) — they're handled internally
                if getattr(tc, "type", "function") != "function":
                    continue
                try:
                    params = json.loads(tc.function.arguments)
                except Exception:
                    params = {}
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, input=params))

        # Extract web search annotations if present
        annotations = getattr(message, "annotations", None) or []
        search_citations = [
            {"url": a.url, "title": a.title}
            for a in annotations
            if getattr(a, "type", "") == "url_citation"
        ]

        metadata: dict[str, Any] = {
            "finish_reason": response.choices[0].finish_reason,
            "raw_tool_calls": [
                {"id": tc.id, "type": tc.type, "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in (message.tool_calls or [])
                if getattr(tc, "type", "function") == "function"
            ],
        }
        if search_citations:
            metadata["web_search_citations"] = search_citations

        return ModelResponse(
            content=content,
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            },
            model=response.model,
            metadata=metadata,
            tool_calls=tool_calls,
        )

    async def stream(self, **kwargs: Any) -> AsyncIterator[str]:
        """Stream chat completion."""
        client = self._get_client()
        messages = kwargs.pop("messages", [])

        stream = await client.chat.completions.create(
            model=self.config.model_name,
            messages=messages,
            stream=True,
            **kwargs,
        )

        async for chunk in stream:
            if not chunk.choices:
                continue
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def close(self) -> None:
        """Close the client."""
        if self._client:
            await self._client.close()
            self._client = None


@ModelRegistry.register("openai", ModelType.VLM)
class OpenAIVLM(VLMInterface):
    """OpenAI VLM implementation (GPT-4V, GPT-4o)."""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self._client = None

    def _get_client(self):
        """Lazy initialization of OpenAI client."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError:
                raise ImportError("openai package required. Install with: pip install openai")

            self._client = AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
            )
        return self._client

    async def analyze(
        self,
        images: list[Union[str, bytes]],
        prompt: str,
        detail: str = "auto",
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> ModelResponse:
        """Analyze images using OpenAI Vision API."""
        client = self._get_client()

        # Build content with images
        content: list[dict[str, Any]] = []

        for image in images:
            if isinstance(image, bytes):
                # Base64 encode bytes
                b64_image = base64.b64encode(image).decode("utf-8")
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64_image}",
                            "detail": detail,
                        },
                    }
                )
            else:
                # Assume it's a URL or file path
                if Path(image).exists():
                    # Validate path doesn't escape CWD or home
                    import os
                    resolved = Path(image).expanduser().resolve()
                    cwd = Path.cwd().resolve()
                    home = Path.home().resolve()
                    if not (
                        str(resolved).startswith(str(cwd) + os.sep) or resolved == cwd
                        or str(resolved).startswith(str(home) + os.sep) or resolved == home
                    ):
                        raise ValueError(f"Path '{resolved}' is outside the allowed directory")
                    # Read file and encode
                    with open(image, "rb") as f:
                        b64_image = base64.b64encode(f.read()).decode("utf-8")
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64_image}",
                                "detail": detail,
                            },
                        }
                    )
                else:
                    # Assume URL
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": image, "detail": detail},
                        }
                    )

        # Add text prompt
        content.append({"type": "text", "text": prompt})

        messages = [{"role": "user", "content": content}]

        request_params: dict[str, Any] = {
            "model": self.config.model_name,
            "messages": messages,
        }

        if max_tokens:
            request_params["max_tokens"] = max_tokens

        response = await client.chat.completions.create(**request_params)

        return ModelResponse(
            content=response.choices[0].message.content,
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            },
            model=response.model,
            metadata={"finish_reason": response.choices[0].finish_reason},
        )

    async def close(self) -> None:
        """Close the client."""
        if self._client:
            await self._client.close()
            self._client = None


@ModelRegistry.register("openai", ModelType.AUDIO)
class OpenAIAudio(AudioModelInterface):
    """OpenAI Audio implementation (Whisper)."""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self._client = None

    def _get_client(self):
        """Lazy initialization of OpenAI client."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError:
                raise ImportError("openai package required. Install with: pip install openai")

            self._client = AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
            )
        return self._client

    async def transcribe(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> ModelResponse:
        """Transcribe audio using OpenAI Whisper API."""
        client = self._get_client()

        # Prepare audio file
        if isinstance(audio, str):
            audio_file = open(audio, "rb")
        else:
            # Create a file-like object from bytes
            import io

            audio_file = io.BytesIO(audio)
            audio_file.name = "audio.mp3"

        try:
            request_params: dict[str, Any] = {
                "model": self.config.model_name or "whisper-1",
                "file": audio_file,
                "response_format": "verbose_json",
            }

            if language:
                request_params["language"] = language
            if prompt:
                request_params["prompt"] = prompt

            response = await client.audio.transcriptions.create(**request_params)

            return ModelResponse(
                content=response.text,
                model=self.config.model_name or "whisper-1",
                metadata={
                    "language": getattr(response, "language", None),
                    "duration": getattr(response, "duration", None),
                    "segments": getattr(response, "segments", []),
                },
            )
        finally:
            if isinstance(audio, str):
                audio_file.close()

    async def close(self) -> None:
        """Close the client."""
        if self._client:
            await self._client.close()
            self._client = None


@ModelRegistry.register("openai", ModelType.EMBEDDING)
class OpenAIEmbedding(EmbeddingModelInterface):
    """OpenAI Embedding implementation (text-embedding-3)."""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self._client = None

    def _get_client(self):
        """Lazy initialization of OpenAI client."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError:
                raise ImportError("openai package required. Install with: pip install openai")

            self._client = AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
            )
        return self._client

    async def embed(
        self,
        texts: Union[str, list[str]],
        **kwargs: Any,
    ) -> ModelResponse:
        """Generate embeddings using OpenAI API."""
        client = self._get_client()

        # Ensure texts is a list
        if isinstance(texts, str):
            texts = [texts]

        response = await client.embeddings.create(
            model=self.config.model_name,
            input=texts,
            **kwargs,
        )

        embeddings = [item.embedding for item in response.data]

        return ModelResponse(
            content=embeddings if len(embeddings) > 1 else embeddings[0],
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "total_tokens": response.usage.total_tokens,
            },
            model=response.model,
            metadata={"dimensions": len(embeddings[0]) if embeddings else 0},
        )

    async def close(self) -> None:
        """Close the client."""
        if self._client:
            await self._client.close()
            self._client = None
