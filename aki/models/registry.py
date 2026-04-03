"""
Model Registry

Provider registration and factory for model instances.
"""

from typing import Optional, Type

from aki.models.base import BaseModelInterface, ModelConfig, ModelType


class ModelRegistry:
    """
    Model Provider Registry.

    Manages registration and instantiation of model providers.
    Uses decorator pattern for easy registration.
    """

    _providers: dict[str, dict[ModelType, Type[BaseModelInterface]]] = {}

    @classmethod
    def register(cls, provider: str, model_type: ModelType):
        """
        Decorator to register a provider implementation.

        Usage:
            @ModelRegistry.register("openai", ModelType.LLM)
            class OpenAILLM(LLMInterface):
                ...
        """

        def decorator(impl_class: Type[BaseModelInterface]) -> Type[BaseModelInterface]:
            if provider not in cls._providers:
                cls._providers[provider] = {}
            cls._providers[provider][model_type] = impl_class
            return impl_class

        return decorator

    @classmethod
    def get(cls, config: ModelConfig, model_type: ModelType) -> BaseModelInterface:
        """
        Get a model instance for the given configuration and type.

        Args:
            config: Model configuration
            model_type: Type of model (LLM, VLM, AUDIO, EMBEDDING)

        Returns:
            Instantiated model interface

        Raises:
            ValueError: If provider or model type is not registered
        """
        if config.provider not in cls._providers:
            available = list(cls._providers.keys())
            raise ValueError(
                f"Provider '{config.provider}' not registered. Available: {available}"
            )

        provider_models = cls._providers[config.provider]
        if model_type not in provider_models:
            available = [t.value for t in provider_models.keys()]
            raise ValueError(
                f"Model type '{model_type.value}' not available for provider "
                f"'{config.provider}'. Available: {available}"
            )

        impl_class = provider_models[model_type]
        return impl_class(config)

    @classmethod
    def get_from_string(
        cls,
        model_string: str,
        model_type: ModelType,
        api_key: Optional[str] = None,
    ) -> BaseModelInterface:
        """
        Get a model instance from a string format.

        Args:
            model_string: Format 'provider:model_name' (e.g., 'openai:gpt-4o')
            model_type: Type of model
            api_key: Optional API key

        Returns:
            Instantiated model interface
        """
        config = ModelConfig.from_string(model_string, api_key)
        return cls.get(config, model_type)

    @classmethod
    def list_providers(cls) -> list[str]:
        """List all registered providers."""
        return list(cls._providers.keys())

    @classmethod
    def list_model_types(cls, provider: str) -> list[ModelType]:
        """List all model types available for a provider."""
        if provider not in cls._providers:
            return []
        return list(cls._providers[provider].keys())

    @classmethod
    def is_registered(cls, provider: str, model_type: ModelType) -> bool:
        """Check if a provider/model_type combination is registered."""
        return provider in cls._providers and model_type in cls._providers[provider]

    @classmethod
    def clear(cls) -> None:
        """Clear all registrations (useful for testing)."""
        cls._providers.clear()
