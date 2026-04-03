"""
Models module - Unified model interface layer.

This module provides a unified abstraction for all model calls,
supporting multiple providers (OpenAI, Anthropic, Google) and
model types (LLM, VLM, Audio, Embedding).
"""

from aki.models.base import (
    BaseModelInterface,
    ModelConfig,
    ModelResponse,
    ModelType,
)
from aki.models.config import (
    ModelSettings,
    get_model_settings,
    reset_model_settings,
)
from aki.models.registry import ModelRegistry

# Import providers to register them
from aki.models.providers import anthropic as _anthropic  # noqa: F401
from aki.models.providers import google as _google  # noqa: F401
from aki.models.providers import openai as _openai  # noqa: F401
from aki.models.providers import qwen as _qwen  # noqa: F401

# Import type interfaces
from aki.models.types.audio import AudioModelInterface
from aki.models.types.embedding import EmbeddingModelInterface
from aki.models.types.llm import LLMInterface
from aki.models.types.vlm import VLMInterface

__all__ = [
    # Base
    "BaseModelInterface",
    "ModelConfig",
    "ModelResponse",
    "ModelType",
    # Registry
    "ModelRegistry",
    # Config
    "ModelSettings",
    "get_model_settings",
    "reset_model_settings",
    # Type interfaces
    "LLMInterface",
    "VLMInterface",
    "AudioModelInterface",
    "EmbeddingModelInterface",
]
