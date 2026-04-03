"""
Anthropic Provider Implementation

Supports Claude models with native server-side web search.
"""

import logging
from typing import Any, AsyncIterator, Optional

from aki.models.base import ModelConfig, ModelResponse, ModelType, ToolCall
from aki.models.registry import ModelRegistry
from aki.models.types.llm import LLMInterface

logger = logging.getLogger(__name__)

# Models that support the server-side web search tool
_WEB_SEARCH_MODELS = {"claude-sonnet-4", "claude-opus-4", "claude-haiku-4"}


def _model_supports_web_search(model_name: str) -> bool:
    return any(prefix in model_name for prefix in _WEB_SEARCH_MODELS)


@ModelRegistry.register("anthropic", ModelType.LLM)
class AnthropicLLM(LLMInterface):
    """Anthropic LLM implementation (Claude) with native web search."""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self._client = None
        self.web_search_enabled: bool = True  # auto-enable for supported models

    def _get_client(self):
        """Lazy initialization of Anthropic client."""
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
            except ImportError:
                raise ImportError(
                    "anthropic package required. Install with: pip install anthropic"
                )

            self._client = AsyncAnthropic(
                api_key=self.config.api_key,
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
        """Chat completion using Anthropic API with optional server-side web search."""
        client = self._get_client()

        # Convert OpenAI-style messages to Anthropic format
        system_message = None
        anthropic_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                anthropic_messages.append(
                    {"role": msg["role"], "content": msg["content"]}
                )

        request_params: dict[str, Any] = {
            "model": self.config.model_name,
            "messages": anthropic_messages,
            "max_tokens": max_tokens or 4096,
            "temperature": temperature,
        }

        if system_message:
            request_params["system"] = system_message

        # Build tools list
        anthropic_tools: list[dict[str, Any]] = []
        if tools:
            for tool in tools:
                if tool.get("type") == "function":
                    func = tool["function"]
                    anthropic_tools.append(
                        {
                            "name": func["name"],
                            "description": func.get("description", ""),
                            "input_schema": func.get("parameters", {}),
                        }
                    )

        # Inject server-side web search for supported models
        if self.web_search_enabled and _model_supports_web_search(self.config.model_name):
            # Remove Tavily web_search/web_read_page — server-side search supersedes them
            anthropic_tools = [
                t for t in anthropic_tools
                if t.get("name") not in ("web_search", "web_read_page")
            ]
            anthropic_tools.append({
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 5,
            })

        if anthropic_tools:
            request_params["tools"] = anthropic_tools

        response = await client.messages.create(**request_params)

        # Extract content, tool calls, and web search results
        content: Any = ""
        tool_calls: list[ToolCall] = []
        raw_blocks = list(response.content)
        search_results: list[dict[str, Any]] = []
        text_parts: list[str] = []

        for block in raw_blocks:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, input=dict(block.input)))
            elif block.type == "server_tool_use":
                # Server-side tool invocation (e.g. web search query) — informational
                logger.debug("Server tool use: %s", getattr(block, "name", "?"))
            elif block.type == "web_search_tool_result":
                # Web search results from server
                if hasattr(block, "content") and isinstance(block.content, list):
                    for hit in block.content:
                        search_results.append({
                            "title": getattr(hit, "title", ""),
                            "url": getattr(hit, "url", ""),
                            "snippet": getattr(hit, "encrypted_content", ""),
                        })

        # Combine all text blocks as the content
        content = "\n".join(text_parts) if text_parts else ""

        metadata: dict[str, Any] = {
            "stop_reason": response.stop_reason,
            "raw_content": raw_blocks,
        }
        if search_results:
            metadata["web_search_results"] = search_results

        return ModelResponse(
            content=content,
            usage={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            },
            model=response.model,
            metadata=metadata,
            tool_calls=tool_calls,
        )

    async def stream(self, **kwargs: Any) -> AsyncIterator[str]:
        """Stream chat completion."""
        client = self._get_client()
        messages = kwargs.pop("messages", [])
        max_tokens = kwargs.pop("max_tokens", 4096)

        # Convert messages
        system_message = None
        anthropic_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                anthropic_messages.append(
                    {"role": msg["role"], "content": msg["content"]}
                )

        request_params: dict[str, Any] = {
            "model": self.config.model_name,
            "messages": anthropic_messages,
            "max_tokens": max_tokens,
        }

        if system_message:
            request_params["system"] = system_message

        async with client.messages.stream(**request_params) as stream:
            async for text in stream.text_stream:
                yield text

    async def close(self) -> None:
        """Close the client."""
        if self._client:
            await self._client.close()
            self._client = None
