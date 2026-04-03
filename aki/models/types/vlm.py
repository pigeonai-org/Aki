"""
VLM Interface

Interface for Vision-Language Models.
"""

from abc import abstractmethod
from typing import Any, Optional, Union

from aki.models.base import BaseModelInterface, ModelResponse, ModelType


class VLMInterface(BaseModelInterface):
    """
    VLM Interface for vision-language models.

    Supports image analysis with text prompts.
    """

    model_type = ModelType.VLM

    @abstractmethod
    async def analyze(
        self,
        images: list[Union[str, bytes]],
        prompt: str,
        detail: str = "auto",
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> ModelResponse:
        """
        Analyze images with a text prompt.

        Args:
            images: List of image URLs or base64-encoded bytes
            prompt: Text prompt describing what to analyze
            detail: Image detail level ('low', 'high', 'auto')
            max_tokens: Maximum tokens to generate
            **kwargs: Additional model-specific parameters

        Returns:
            ModelResponse with analysis result
        """
        pass

    async def invoke(self, **kwargs: Any) -> ModelResponse:
        """Invoke the model using analyze interface."""
        images = kwargs.pop("images", [])
        prompt = kwargs.pop("prompt", "")
        return await self.analyze(images, prompt, **kwargs)

    async def stream(self, **kwargs: Any):
        """Stream is not implemented by default - subclasses should override."""
        raise NotImplementedError("Streaming not implemented for this VLM")
