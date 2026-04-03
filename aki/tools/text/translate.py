"""
Translation Tool

Translate text using LLM.
Pure executor - no decision making.
"""

from typing import Any, Optional

from aki.config import get_settings
from aki.models import LLMInterface, ModelConfig, ModelRegistry, ModelType
from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.registry import ToolRegistry


def _get_default_llm_config() -> ModelConfig:
    """Get default LLM config with API key from settings."""
    settings = get_settings()
    config = ModelConfig.from_string(settings.default_llm)
    config.api_key = settings.openai_api_key
    if settings.openai_base_url:
        config.base_url = settings.openai_base_url
    return config


@ToolRegistry.register
class TranslateTool(BaseTool):
    """
    Text translation tool.

    Translates text using LLM-based translation.
    """

    name = "translate_text"
    description = "Translate text from one language to another using LLM"
    parameters = [
        ToolParameter(
            name="text",
            type="string",
            description="Text to translate",
        ),
    ]
    concurrency_safe = True

    def __init__(
        self,
        llm_model: Optional[LLMInterface] = None,
        model_config: Optional[ModelConfig] = None,
    ):
        """
        Initialize the translation tool.

        Args:
            llm_model: Pre-configured LLM interface
            model_config: Model configuration (auto-configured with API key if not provided)
        """
        super().__init__()
        self._llm_model = llm_model
        self._model_config = model_config or _get_default_llm_config()

    def _get_model(self) -> LLMInterface:
        """Get the LLM model (lazy initialization)."""
        if self._llm_model is None:
            self._llm_model = ModelRegistry.get(self._model_config, ModelType.LLM)
        return self._llm_model

    async def execute(
        self,
        text: str,
        target_language: str,
        source_language: str = "auto",
        style: str = "natural",
        **kwargs: Any,
    ) -> ToolResult:
        """
        Execute translation.

        Args:
            text: Text to translate
            target_language: Target language
            source_language: Source language
            style: Translation style

        Returns:
            ToolResult with translation
        """
        try:
            model = self._get_model()

            # Build translation prompt
            system_prompt = f"""You are a professional translator. 
Translate the following text to {target_language}.
Style: {style}
Only output the translation, nothing else."""

            if source_language != "auto":
                system_prompt += f"\nSource language: {source_language}"

            response = await model.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                temperature=0.3,  # Lower temperature for more consistent translations
            )

            return ToolResult.ok(
                data={
                    "translation": response.content,
                    "source_language": source_language,
                    "target_language": target_language,
                },
                model=response.model,
                usage=response.usage,
            )
        except Exception as e:
            return ToolResult.fail(f"Translation failed: {str(e)}")


@ToolRegistry.register
class ProofreadTool(BaseTool):
    """
    Text proofreading tool.

    Reviews and corrects translated text.
    """

    name = "proofread_text"
    description = "Proofread and correct translated text for quality"
    parameters = [
        ToolParameter(
            name="text",
            type="string",
            description="Text to proofread",
        ),
        ToolParameter(
            name="language",
            type="string",
            description="Language of the text",
        ),
        ToolParameter(
            name="context",
            type="string",
            description="Additional context for proofreading",
            required=False,
        ),
    ]
    concurrency_safe = True

    def __init__(
        self,
        llm_model: Optional[LLMInterface] = None,
        model_config: Optional[ModelConfig] = None,
    ):
        super().__init__()
        self._llm_model = llm_model
        self._model_config = model_config or _get_default_llm_config()

    def _get_model(self) -> LLMInterface:
        if self._llm_model is None:
            self._llm_model = ModelRegistry.get(self._model_config, ModelType.LLM)
        return self._llm_model

    async def execute(
        self,
        text: str,
        language: str,
        context: Optional[str] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """
        Execute proofreading.

        Args:
            text: Text to proofread
            language: Language of the text
            context: Additional context

        Returns:
            ToolResult with corrections
        """
        try:
            model = self._get_model()

            system_prompt = f"""You are a professional proofreader for {language} text.
Review the text and provide corrections if needed.
Respond with JSON: {{"corrected_text": "...", "changes": ["..."], "is_changed": true/false}}"""

            if context:
                system_prompt += f"\nContext: {context}"

            response = await model.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                temperature=0.2,
            )

            # Parse response
            import json

            try:
                result = json.loads(response.content)
            except json.JSONDecodeError:
                result = {
                    "corrected_text": response.content,
                    "changes": [],
                    "is_changed": False,
                }

            return ToolResult.ok(
                data=result,
                model=response.model,
            )
        except Exception as e:
            return ToolResult.fail(f"Proofreading failed: {str(e)}")
