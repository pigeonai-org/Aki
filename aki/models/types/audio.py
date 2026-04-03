"""
Audio Model Interface

Interface for Audio/Speech Recognition Models.
"""

from abc import abstractmethod
from typing import Any, Optional, Union

from aki.models.base import BaseModelInterface, ModelResponse, ModelType


class AudioModelInterface(BaseModelInterface):
    """
    Audio Model Interface for speech recognition.

    Supports transcription of audio to text.
    """

    model_type = ModelType.AUDIO

    @abstractmethod
    async def transcribe(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> ModelResponse:
        """
        Transcribe audio to text.

        Args:
            audio: Audio file path or bytes
            language: Source language code (e.g., 'en', 'zh')
            prompt: Optional prompt to guide transcription
            **kwargs: Additional model-specific parameters

        Returns:
            ModelResponse with transcription result and segments
        """
        pass

    async def invoke(self, **kwargs: Any) -> ModelResponse:
        """Invoke the model using transcribe interface."""
        audio = kwargs.pop("audio", "")
        return await self.transcribe(audio, **kwargs)

    async def stream(self, **kwargs: Any):
        """Stream is not implemented for audio models."""
        raise NotImplementedError("Streaming not implemented for audio models")
