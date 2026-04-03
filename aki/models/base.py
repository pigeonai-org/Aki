"""
Model Base Classes

Unified abstraction layer for all model calls.
Supports multiple providers and model types.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, AsyncIterator, Optional

from pydantic import BaseModel, Field


class ModelType(Enum):
    """Supported model types."""

    LLM = "llm"  # Text generation
    VLM = "vlm"  # Vision-language
    AUDIO = "audio"  # Speech recognition
    EMBEDDING = "embedding"  # Vector embedding


class ModelConfig(BaseModel):
    """Model configuration."""

    provider: str = Field(..., description="Provider name (openai, anthropic, google, local)")
    model_name: str = Field(..., description="Model name (gpt-4o, claude-3, gemini-2.0-flash)")
    api_key: Optional[str] = Field(default=None, repr=False, description="API key (optional, uses env if not set)")
    base_url: Optional[str] = Field(default=None, description="Custom API endpoint")
    extra_params: dict[str, Any] = Field(default_factory=dict, description="Additional parameters")

    @classmethod
    def from_string(cls, model_string: str, api_key: Optional[str] = None) -> "ModelConfig":
        """
        Create config from string format 'provider:model_name'.

        Example: 'openai:gpt-4o' -> ModelConfig(provider='openai', model_name='gpt-4o')
        """
        if ":" not in model_string:
            raise ValueError(f"Invalid model string format: {model_string}. Expected 'provider:model_name'")
        provider, model_name = model_string.split(":", 1)
        return cls(provider=provider, model_name=model_name, api_key=api_key)


class ToolCall(BaseModel):
    """A single tool call requested by the model."""

    id: str = Field(..., description="Unique tool call identifier")
    name: str = Field(..., description="Tool name")
    input: dict[str, Any] = Field(default_factory=dict, description="Tool input parameters")


class ModelResponse(BaseModel):
    """Unified model response."""

    content: Any = Field(..., description="Response content (text string when no tool calls)")
    usage: Optional[dict[str, int]] = Field(default=None, description="Token usage statistics")
    model: str = Field(..., description="Model name used")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    tool_calls: list[ToolCall] = Field(default_factory=list, description="Tool calls requested by the model")


class BaseModelInterface(ABC):
    """
    Abstract base class for all model interfaces.

    All model implementations must inherit from this class.
    """

    model_type: ModelType

    def __init__(self, config: ModelConfig):
        """Initialize the model interface with configuration."""
        self.config = config
        self._client: Any = None

    @property
    def provider(self) -> str:
        """Get the provider name."""
        return self.config.provider

    @property
    def model_name(self) -> str:
        """Get the model name."""
        return self.config.model_name

    @abstractmethod
    async def invoke(self, **kwargs: Any) -> ModelResponse:
        """
        Invoke the model synchronously.

        Args:
            **kwargs: Model-specific parameters

        Returns:
            ModelResponse with the result
        """
        pass

    @abstractmethod
    async def stream(self, **kwargs: Any) -> AsyncIterator[str]:
        """
        Stream the model response.

        Args:
            **kwargs: Model-specific parameters

        Yields:
            String chunks of the response
        """
        pass

    async def __aenter__(self) -> "BaseModelInterface":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def close(self) -> None:
        """Close any open connections."""
        pass
