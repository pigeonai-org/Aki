"""
Vision Analysis Tool

Analyze images using vision-language models.
Pure executor - no decision making.
"""

from typing import Any, Optional, Union

from aki.config import get_settings
from aki.models import ModelConfig, ModelRegistry, ModelType, VLMInterface
from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.registry import ToolRegistry


def _get_default_vlm_config() -> ModelConfig:
    """Get default VLM config with API key from settings."""
    settings = get_settings()
    config = ModelConfig.from_string(settings.default_vlm)
    if config.provider == "openai":
        config.api_key = settings.openai_api_key
        if settings.openai_base_url:
            config.base_url = settings.openai_base_url
    elif config.provider == "anthropic":
        config.api_key = settings.anthropic_api_key
    elif config.provider == "google":
        config.api_key = settings.google_api_key
    return config


@ToolRegistry.register
class VisionAnalyzeTool(BaseTool):
    """
    Vision analysis tool.

    Analyzes images using vision-language models (GPT-4V, etc.).
    """

    name = "vision_analyze"
    description = "Analyze images using vision-language models"
    parameters = [
        ToolParameter(
            name="images",
            type="array",
            description="List of image paths or URLs to analyze",
        ),
        ToolParameter(
            name="prompt",
            type="string",
            description="Analysis prompt/question about the images",
        ),
    ]
    concurrency_safe = True

    def __init__(
        self,
        vlm_model: Optional[VLMInterface] = None,
        model_config: Optional[ModelConfig] = None,
    ):
        """
        Initialize the vision analysis tool.

        Args:
            vlm_model: Pre-configured VLM interface
            model_config: Model configuration (auto-configured with API key if not provided)
        """
        super().__init__()
        self._vlm_model = vlm_model
        self._model_config = model_config or _get_default_vlm_config()

    def _get_model(self) -> VLMInterface:
        """Get the VLM model (lazy initialization)."""
        if self._vlm_model is None:
            if not ModelRegistry.is_registered(self._model_config.provider, ModelType.VLM):
                available = [
                    provider
                    for provider in ModelRegistry.list_providers()
                    if ModelRegistry.is_registered(provider, ModelType.VLM)
                ]
                raise ValueError(
                    f"VLM provider '{self._model_config.provider}' is not available. "
                    f"Available VLM providers: {available}"
                )
            self._vlm_model = ModelRegistry.get(self._model_config, ModelType.VLM)
        return self._vlm_model

    async def execute(
        self,
        images: list[Union[str, bytes]],
        prompt: str,
        detail: str = "auto",
        **kwargs: Any,
    ) -> ToolResult:
        """
        Execute image analysis.

        Args:
            images: List of image paths or URLs
            prompt: Analysis prompt
            detail: Image detail level

        Returns:
            ToolResult with analysis
        """
        try:
            model = self._get_model()
            response = await model.analyze(
                images=images,
                prompt=prompt,
                detail=detail,
            )

            return ToolResult.ok(
                data={
                    "analysis": response.content,
                },
                model=response.model,
                usage=response.usage,
            )
        except Exception as e:
            return ToolResult.fail(f"Vision analysis failed: {str(e)}")
