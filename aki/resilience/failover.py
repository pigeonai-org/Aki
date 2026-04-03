"""
Model Failover

Wraps LLMInterface with automatic provider failover on errors.
Transparently switches to the next model in the chain when a provider fails.
"""

import logging
from typing import Any, AsyncIterator, Optional

from pydantic import BaseModel, Field

from aki.models.base import BaseModelInterface, ModelConfig, ModelResponse, ModelType

logger = logging.getLogger(__name__)


class FailoverChain(BaseModel):
    """
    Ordered list of model identifiers to try.

    Example::

        chain = FailoverChain(models=[
            "anthropic:claude-sonnet-4-20250514",
            "openai:gpt-4o",
            "google:gemini-2.0-flash",
        ])
    """

    models: list[str] = Field(
        ...,
        min_length=1,
        description="Ordered model identifiers (provider:model_name)",
    )


class ModelFailover(BaseModelInterface):
    """
    LLMInterface wrapper that automatically fails over to the next provider.

    IS-A BaseModelInterface, so it can be used anywhere an LLM is expected.
    Wraps multiple LLM instances and tries them in order until one succeeds.

    Usage::

        from aki.models.registry import ModelRegistry

        chain = FailoverChain(models=["anthropic:claude-sonnet-4-20250514", "openai:gpt-4o"])
        failover = ModelFailover(chain, model_factory=ModelRegistry.create_llm)
        response = await failover.chat(messages)
    """

    model_type = ModelType.LLM

    def __init__(
        self,
        chain: FailoverChain,
        model_factory: Any = None,
        settings: Any = None,
    ) -> None:
        """
        Args:
            chain: Failover chain of model identifiers.
            model_factory: Callable(model_string) -> LLMInterface.
                           If None, models must be set via set_models().
            settings: Application settings for API key resolution.
        """
        # Use the first model's config as our own
        config = ModelConfig.from_string(chain.models[0])
        super().__init__(config)
        self.chain = chain
        self._model_factory = model_factory
        self._settings = settings
        self._models: list[Any] = []  # Lazily initialized LLM instances
        self._current_index = 0

    async def _ensure_models(self) -> None:
        """Lazily initialize LLM instances from the chain."""
        if self._models:
            return
        if self._model_factory is None:
            raise RuntimeError("ModelFailover requires either model_factory or pre-set models via set_models()")
        for model_str in self.chain.models:
            try:
                llm = self._model_factory(model_str)
                self._models.append(llm)
            except Exception:
                logger.warning("Failed to create LLM for %s, skipping", model_str)

        if not self._models:
            raise RuntimeError(f"No models could be initialized from chain: {self.chain.models}")

    def set_models(self, models: list[Any]) -> None:
        """Directly set pre-created LLM instances (for testing or manual setup)."""
        self._models = models

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> ModelResponse:
        """
        Chat with automatic failover.

        Tries each model in the chain. On failure, logs the error and
        advances to the next provider.
        """
        await self._ensure_models()

        last_error: Exception | None = None
        # Try from current index, then wrap around
        for offset in range(len(self._models)):
            idx = (self._current_index + offset) % len(self._models)
            model = self._models[idx]
            model_name = self.chain.models[idx] if idx < len(self.chain.models) else "unknown"

            try:
                response = await model.chat(
                    messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
                # Success: update current index for next call
                self._current_index = idx
                return response
            except Exception as e:
                last_error = e
                logger.warning(
                    "Model %s failed (%s: %s), trying next...",
                    model_name,
                    type(e).__name__,
                    str(e)[:200],
                )

        raise RuntimeError(
            f"All models in failover chain exhausted. Last error: {last_error}"
        )

    async def invoke(self, **kwargs: Any) -> ModelResponse:
        """Invoke via chat interface."""
        messages = kwargs.pop("messages", [])
        return await self.chat(messages, **kwargs)

    async def stream(self, **kwargs: Any) -> AsyncIterator[str]:
        """Streaming failover - tries current model's stream method."""
        await self._ensure_models()
        model = self._models[self._current_index]
        async for chunk in model.stream(**kwargs):
            yield chunk

    @property
    def current_model(self) -> str:
        """The model identifier currently in use."""
        if self._current_index < len(self.chain.models):
            return self.chain.models[self._current_index]
        return "unknown"

    def reset(self) -> None:
        """Reset to the first (preferred) model in the chain."""
        self._current_index = 0
