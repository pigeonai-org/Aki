"""
Google Provider Implementation

Supports Gemini models for LLM, VLM, and Audio.
"""

from typing import Any, AsyncIterator, Optional, Union

from aki.models.base import ModelConfig, ModelResponse, ModelType
from aki.models.registry import ModelRegistry
from aki.models.types.audio import AudioModelInterface
from aki.models.types.llm import LLMInterface


@ModelRegistry.register("google", ModelType.LLM)
class GeminiLLM(LLMInterface):
    """Google Gemini LLM implementation."""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self._client = None

    def _get_client(self):
        """Lazy initialization of Gemini client."""
        if self._client is None:
            try:
                import google.generativeai as genai
            except ImportError:
                raise ImportError(
                    "google-generativeai package required. Install with: pip install google-generativeai"
                )

            genai.configure(api_key=self.config.api_key)
            self._client = genai.GenerativeModel(self.config.model_name)
        return self._client

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> ModelResponse:
        """Chat completion using Gemini API."""
        model = self._get_client()

        # Convert messages to Gemini format
        gemini_messages = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            gemini_messages.append({"role": role, "parts": [msg["content"]]})

        # Generate response
        generation_config = {"temperature": temperature}
        if max_tokens:
            generation_config["max_output_tokens"] = max_tokens

        response = await model.generate_content_async(
            gemini_messages,
            generation_config=generation_config,
        )

        return ModelResponse(
            content=response.text,
            usage={
                "prompt_tokens": getattr(
                    response.usage_metadata, "prompt_token_count", 0
                ),
                "completion_tokens": getattr(
                    response.usage_metadata, "candidates_token_count", 0
                ),
                "total_tokens": getattr(
                    response.usage_metadata, "total_token_count", 0
                ),
            },
            model=self.config.model_name,
            metadata={},
        )

    async def stream(self, **kwargs: Any) -> AsyncIterator[str]:
        """Stream is not fully implemented for Gemini."""
        raise NotImplementedError("Streaming not yet implemented for Gemini")


@ModelRegistry.register("google", ModelType.AUDIO)
class GeminiAudio(AudioModelInterface):
    """Google Gemini Audio implementation for speech recognition."""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self._client = None

    def _get_client(self):
        """Lazy initialization of Gemini client."""
        if self._client is None:
            try:
                import google.generativeai as genai
            except ImportError:
                raise ImportError(
                    "google-generativeai package required. Install with: pip install google-generativeai"
                )

            genai.configure(api_key=self.config.api_key)
            self._client = genai.GenerativeModel(self.config.model_name)
        return self._client

    async def transcribe(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> ModelResponse:
        """Transcribe audio using Gemini API."""
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError(
                "google-generativeai package required. Install with: pip install google-generativeai"
            )

        model = self._get_client()

        # Prepare audio file
        if isinstance(audio, str):
            audio_file = genai.upload_file(audio)
        else:
            # Save bytes to temp file and upload
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(audio)
                temp_path = f.name

            audio_file = genai.upload_file(temp_path)

        # Build prompt
        transcription_prompt = prompt or "Transcribe this audio accurately."
        if language:
            transcription_prompt = f"Transcribe this audio in {language}. {transcription_prompt}"

        # Generate transcription
        response = await model.generate_content_async([audio_file, transcription_prompt])

        return ModelResponse(
            content=response.text,
            model=self.config.model_name,
            metadata={
                "language": language,
            },
        )
