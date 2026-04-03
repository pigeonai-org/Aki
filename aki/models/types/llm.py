"""
LLM Interface

Interface for Large Language Models (text generation).
"""

from abc import abstractmethod
from typing import Any, Optional

from aki.models.base import BaseModelInterface, ModelResponse, ModelType


class LLMInterface(BaseModelInterface):
    """
    LLM Interface for text generation models.

    Supports chat completion with optional tool/function calling.
    """

    model_type = ModelType.LLM

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> ModelResponse:
        """
        Chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions for function calling
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional model-specific parameters

        Returns:
            ModelResponse with generated text and optional tool calls
        """
        pass

    async def invoke(self, **kwargs: Any) -> ModelResponse:
        """Invoke the model using chat interface."""
        messages = kwargs.pop("messages", [])
        return await self.chat(messages, **kwargs)

    async def stream(self, **kwargs: Any):
        """Stream is not implemented by default - subclasses should override."""
        raise NotImplementedError("Streaming not implemented for this LLM")
