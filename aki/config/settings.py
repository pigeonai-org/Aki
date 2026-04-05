"""
Aki Global Configuration

Centralized configuration management using Pydantic Settings.
Supports environment variables and .env files.
"""

import os
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    """Agent system configuration."""

    max_agents_per_task: int = Field(
        default=5,
        description="Maximum number of agents allowed per task",
    )
    max_agent_depth: int = Field(
        default=3,
        description="Maximum agent call chain depth (prevents infinite recursion)",
    )
    agents_dir: str = Field(
        default=".aki/agents",
        description="Directory for agent definition files (agent.md frontmatter)",
    )

    model_config = SettingsConfigDict(env_prefix="AKI_")


class MemorySettings(BaseSettings):
    """Memory system configuration."""

    window_size: int = Field(
        default=20,
        description="Sliding window size used by short-term selection strategy",
    )
    short_term_max_items_per_task: int = Field(
        default=300,
        description="Maximum short-term memory items retained per task",
    )
    short_term_observe_limit: int = Field(
        default=12,
        description="Default number of short-term memories injected into observations",
    )
    default_namespace: str = Field(
        default="default",
        description="Default namespace for memory partitioning",
    )
    long_term_memory_dir: str = Field(
        default=".aki/long-term-memory",
        description="Directory for human-readable long-term memory .md files",
    )
    memory_review_enabled: bool = Field(
        default=True,
        description="Run a post-turn memory review pass after each agent response (legacy, superseded by review_enabled)",
    )
    # Session memory
    session_dir: str = Field(
        default=".aki/sessions",
        description="Directory for persistent session storage",
    )
    # Long-term dimensions base
    memory_base_dir: str = Field(
        default=".aki/memory",
        description="Base directory for all long-term memory dimensions",
    )
    # Review
    review_enabled: bool = Field(
        default=True,
        description="Run post-session memory review pass",
    )
    review_min_messages: int = Field(
        default=3,
        description="Minimum user messages before triggering review",
    )
    # Recall
    episodic_recall_limit: int = Field(
        default=5,
        description="Number of recent episodes to inject at session start",
    )
    semantic_recall_limit: int = Field(
        default=10,
        description="Number of semantic entries to inject at session start",
    )

    model_config = SettingsConfigDict(env_prefix="AKI_MEMORY_")


class ContextSettings(BaseSettings):
    """Context management configuration."""

    max_context_tokens: int = Field(
        default=128_000,
        description="Maximum context window tokens for the primary model",
    )
    compaction_threshold: float = Field(
        default=0.75,
        description="Fraction of message budget that triggers compaction (0.0-1.0)",
    )
    reserve_tokens: int = Field(
        default=4_000,
        description="Token buffer reserved for model output",
    )
    max_compaction_failures: int = Field(
        default=3,
        description="Consecutive compaction failures before circuit breaker trips",
    )

    model_config = SettingsConfigDict(env_prefix="AKI_CONTEXT_")


class ResilienceSettings(BaseSettings):
    """Resilience / error recovery configuration."""

    failover_models: list[str] = Field(
        default_factory=lambda: ["openai:gpt-4o", "anthropic:claude-sonnet-4-20250514"],
        description="Ordered list of fallback models for provider failover",
    )
    backoff_base_delay: float = Field(
        default=1.0,
        description="Base delay in seconds for exponential backoff",
    )
    backoff_max_delay: float = Field(
        default=60.0,
        description="Maximum delay in seconds for exponential backoff",
    )
    backoff_max_retries: int = Field(
        default=5,
        description="Maximum number of retries for rate-limited requests",
    )
    max_consecutive_errors: int = Field(
        default=3,
        description="Consecutive errors before circuit breaker aborts the agent loop",
    )

    model_config = SettingsConfigDict(env_prefix="AKI_RESILIENCE_")


class HookSettings(BaseSettings):
    """Hook + permission system configuration."""

    enabled: bool = Field(
        default=True,
        description="Enable the hook/event system (disable for minimal overhead)",
    )
    default_permission_mode: str = Field(
        default="default",
        description="Default permission mode for agents without an explicit setting (bypass|default|auto|strict|plan)",
    )

    model_config = SettingsConfigDict(env_prefix="AKI_HOOKS_")


class GatewaySettings(BaseSettings):
    """Gateway configuration for multi-platform messaging."""

    discord_token: Optional[str] = Field(
        default=None, description="Discord bot token"
    )
    discord_channel_ids: Optional[str] = Field(
        default=None,
        description="Comma-separated allowed Discord channel IDs (empty = all)",
    )
    session_dir: str = Field(
        default=".aki/sessions",
        description="Directory for JSONL session persistence",
    )
    compaction_max_tokens: int = Field(
        default=8000,
        description="Max estimated context tokens before compaction triggers",
    )
    compaction_threshold: float = Field(
        default=0.80,
        description="Fraction of max_tokens that triggers compaction (0.0-1.0)",
    )
    default_role: str = Field(
        default="orchestrator", description="Default agent role for gateway sessions"
    )
    default_llm: str = Field(
        default="openai:gpt-4o", description="Default LLM for gateway sessions"
    )

    model_config = SettingsConfigDict(env_prefix="AKI_GATEWAY_", env_file=".env", env_file_encoding="utf-8", extra="ignore")



class Settings(BaseSettings):
    """Main application settings."""

    # API Keys (supports both AKI_* and standard env vars as fallback)
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API Key", repr=False)
    anthropic_api_key: Optional[str] = Field(default=None, description="Anthropic API Key", repr=False)
    google_api_key: Optional[str] = Field(default=None, description="Google API Key", repr=False)
    dashscope_api_key: Optional[str] = Field(default=None, description="DashScope API Key", repr=False)
    pyannote_api_key: Optional[str] = Field(default=None, description="Pyannote API Key", repr=False)
    tavily_api_key: Optional[str] = Field(default=None, description="Tavily API Key", repr=False)

    # Default model configurations (format: provider:model_name)
    default_llm: str = Field(default="openai:gpt-4o", description="Default LLM model")
    default_vlm: str = Field(default="openai:gpt-4o", description="Default VLM model")
    default_audio: str = Field(default="qwen:qwen3-asr-flash", description="Default audio model")
    default_embedding: str = Field(
        default="openai:text-embedding-3-small", description="Default embedding model"
    )

    # Sandbox / working directory
    sandbox_dir: Optional[str] = Field(
        default=None,
        description=(
            "Root directory for file tool access. Defaults to CWD if not set. "
            "In Gateway/multi-user mode, set this to restrict file access."
        ),
    )

    # Custom endpoints
    openai_base_url: Optional[str] = Field(
        default=None, description="Custom OpenAI-compatible endpoint"
    )

    # Nested settings
    agent: AgentSettings = Field(default_factory=AgentSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    context: ContextSettings = Field(default_factory=ContextSettings)
    resilience: ResilienceSettings = Field(default_factory=ResilienceSettings)
    hooks: HookSettings = Field(default_factory=HookSettings)
    gateway: GatewaySettings = Field(default_factory=GatewaySettings)
    model_config = SettingsConfigDict(
        env_prefix="AKI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def fallback_openai_key(cls, v: Optional[str]) -> Optional[str]:
        """Fallback to OPENAI_API_KEY if AKI_OPENAI_API_KEY not set."""
        if v is None:
            return os.environ.get("OPENAI_API_KEY")
        return v

    @field_validator("anthropic_api_key", mode="before")
    @classmethod
    def fallback_anthropic_key(cls, v: Optional[str]) -> Optional[str]:
        """Fallback to ANTHROPIC_API_KEY if AKI_ANTHROPIC_API_KEY not set."""
        if v is None:
            return os.environ.get("ANTHROPIC_API_KEY")
        return v

    @field_validator("google_api_key", mode="before")
    @classmethod
    def fallback_google_key(cls, v: Optional[str]) -> Optional[str]:
        """Fallback to GOOGLE_API_KEY if AKI_GOOGLE_API_KEY not set."""
        if v is None:
            return os.environ.get("GOOGLE_API_KEY")
        return v

    @field_validator("tavily_api_key", mode="before")
    @classmethod
    def fallback_tavily_key(cls, v: Optional[str]) -> Optional[str]:
        """Fallback to TAVILY_API_KEY if AKI_TAVILY_API_KEY not set."""
        if v is None:
            return os.environ.get("TAVILY_API_KEY")
        return v

    @field_validator("dashscope_api_key", mode="before")
    @classmethod
    def fallback_dashscope_key(cls, v: Optional[str]) -> Optional[str]:
        """Fallback to DASHSCOPE_API_KEY if AKI_DASHSCOPE_API_KEY not set."""
        if v is None:
            return os.environ.get("DASHSCOPE_API_KEY")
        return v

    @field_validator("pyannote_api_key", mode="before")
    @classmethod
    def fallback_pyannote_key(cls, v: Optional[str]) -> Optional[str]:
        """Fallback to PYANNOTE_API_KEY if AKI_PYANNOTE_API_KEY not set."""
        if v is None:
            return os.environ.get("PYANNOTE_API_KEY")
        return v


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the global settings instance (singleton)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Reset the global settings instance (useful for testing)."""
    global _settings
    _settings = None
