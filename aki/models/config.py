"""
Model Configuration

Centralized model API key and configuration management.
"""

import os
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from aki.models.base import ModelConfig, ModelType


class ModelSettings(BaseSettings):
    """
    Model API configuration.

    Supports environment variables and .env files.
    All keys are prefixed with AKI_.
    """

    # API Keys
    openai_api_key: Optional[str] = Field(
        default=None,
        description="OpenAI API Key",
    )
    anthropic_api_key: Optional[str] = Field(
        default=None,
        description="Anthropic API Key",
    )
    google_api_key: Optional[str] = Field(
        default=None,
        description="Google API Key",
    )
    dashscope_api_key: Optional[str] = Field(
        default=None,
        description="DashScope API Key",
    )

    # Default model configurations (format: provider:model_name)
    default_llm: str = Field(
        default="openai:gpt-4o",
        description="Default LLM model",
    )
    default_vlm: str = Field(
        default="openai:gpt-4o",
        description="Default VLM model",
    )
    default_audio: str = Field(
        default="qwen:qwen3-asr-flash",
        description="Default audio model",
    )
    default_embedding: str = Field(
        default="openai:text-embedding-3-small",
        description="Default embedding model",
    )

    # Custom endpoints
    openai_base_url: Optional[str] = Field(
        default=None,
        description="Custom OpenAI-compatible endpoint",
    )

    model_config = SettingsConfigDict(
        env_prefix="AKI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def get_api_key(self, provider: str) -> Optional[str]:
        """Get the API key for a provider."""
        key_map = {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "google": self.google_api_key,
            "qwen": self.dashscope_api_key,
        }
        return key_map.get(provider)

    @field_validator("dashscope_api_key", mode="before")
    @classmethod
    def fallback_dashscope_key(cls, v: Optional[str]) -> Optional[str]:
        """Fallback to DASHSCOPE_API_KEY if AKI_DASHSCOPE_API_KEY not set."""
        if v is None:
            return os.environ.get("DASHSCOPE_API_KEY")
        return v

    def get_default_config(self, model_type: ModelType) -> ModelConfig:
        """Get the default model configuration for a model type."""
        type_to_default = {
            ModelType.LLM: self.default_llm,
            ModelType.VLM: self.default_vlm,
            ModelType.AUDIO: self.default_audio,
            ModelType.EMBEDDING: self.default_embedding,
        }

        model_string = type_to_default.get(model_type, self.default_llm)
        config = ModelConfig.from_string(model_string)

        # Add API key if available
        api_key = self.get_api_key(config.provider)
        if api_key:
            config.api_key = api_key

        # Add custom base URL for OpenAI
        if config.provider == "openai" and self.openai_base_url:
            config.base_url = self.openai_base_url

        return config


# Global settings instance
_model_settings: Optional[ModelSettings] = None


def get_model_settings() -> ModelSettings:
    """Get the global model settings instance (singleton)."""
    global _model_settings
    if _model_settings is None:
        _model_settings = ModelSettings()
    return _model_settings


def reset_model_settings() -> None:
    """Reset the global model settings instance (useful for testing)."""
    global _model_settings
    _model_settings = None
