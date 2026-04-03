"""Subtitle proofreading tool."""

import json
from typing import Any, Optional

from aki.config import get_settings
from aki.models import LLMInterface, ModelConfig, ModelRegistry, ModelType
from aki.tools.base import BaseTool, ToolParameter, ToolResult
from aki.tools.io.srt import SubtitleEntry
from aki.tools.registry import ToolRegistry


def _get_default_llm_config() -> ModelConfig:
    """Get default LLM config."""
    settings = get_settings()
    config = ModelConfig.from_string(settings.default_llm)
    config.api_key = settings.openai_api_key
    if settings.openai_base_url:
        config.base_url = settings.openai_base_url
    return config


@ToolRegistry.register
class SubtitleProofreadTool(BaseTool):
    """Review translated subtitle entries and return suggestions only."""

    name = "subtitle_proofread"
    description = "Review translated subtitles and provide non-mutating suggestions"
    parameters = [
        ToolParameter(
            name="subtitles",
            type="array",
            description="List of subtitle entries",
        ),
        ToolParameter(
            name="target_language",
            type="string",
            description="Target language code",
        ),
        ToolParameter(
            name="context",
            type="string",
            description="Additional context",
            required=False,
        ),
    ]

    def __init__(
        self,
        llm_model: Optional[LLMInterface] = None,
        model_config: Optional[ModelConfig] = None,
        rag: Optional[Any] = None,
    ):
        super().__init__()
        self._llm_model = llm_model
        self._model_config = model_config or _get_default_llm_config()
        self.rag = rag

    def _get_model(self) -> LLMInterface:
        if self._llm_model is None:
            self._llm_model = ModelRegistry.get(self._model_config, ModelType.LLM)
        return self._llm_model

    async def execute(
        self,
        subtitles: list[dict[str, Any]],
        target_language: str,
        context: Optional[str] = None,
        batch_size: int = 5,
        max_suggestions: int = 50,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute subtitle proofreading."""
        if batch_size < 1:
            return ToolResult.fail("batch_size must be >= 1")
        if max_suggestions < 1:
            return ToolResult.fail("max_suggestions must be >= 1")

        try:
            entries = [SubtitleEntry(**s) for s in subtitles]
            suggestions = await self._collect_suggestions(
                entries=entries,
                language=target_language,
                context=context,
                batch_size=batch_size,
            )
            suggestions = suggestions[:max_suggestions]

            return ToolResult.ok(
                data={
                    "subtitles": [s.model_dump() for s in entries],
                    "count": len(entries),
                    "suggestions": suggestions,
                    "suggestion_count": len(suggestions),
                }
            )
        except Exception as e:
            return ToolResult.fail(f"Proofreading failed: {str(e)}")

    async def _collect_suggestions(
        self,
        entries: list[SubtitleEntry],
        language: str,
        context: Optional[str],
        batch_size: int,
    ) -> list[dict[str, Any]]:
        """Collect review suggestions in batches without mutating entries."""
        model = self._get_model()
        all_suggestions: list[dict[str, Any]] = []

        for offset in range(0, len(entries), batch_size):
            batch = entries[offset : offset + batch_size]
            prompt = self._build_batch_prompt(batch, language, context)

            try:
                response = await model.chat(
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a professional subtitle proofreader.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.0,
                )
                all_suggestions.extend(self._parse_response(response.content))
            except Exception:
                pass

        return all_suggestions

    def _build_batch_prompt(
        self,
        batch: list[SubtitleEntry],
        language: str,
        context: Optional[str],
    ) -> str:
        """Build prompt for one proofreading batch."""
        segments_text = "\n".join(
            (
                f"ID: {entry.index}\n"
                f"Original: {entry.src_text or entry.text}\n"
                f"Translation: {entry.translation or entry.text}\n"
            )
            for entry in batch
        )

        return f"""Review the following subtitle segments translated into {language}.
Check for accuracy, fluency, terminology consistency, and subtitle readability.
If a translation is good, do not suggest changes.
If improvements are needed, provide concise suggestions.
Do NOT rewrite subtitles directly in-place.

Context: {context or "None"}

Segments:
{segments_text}

Output valid JSON only:
{{
  "suggestions": [
    {{
      "id": <index>,
      "suggestion": "<improved_text>",
      "issue_type": "<accuracy|fluency|terminology|style|timing>",
      "severity": "<low|medium|high>",
      "rationale": "<short reason>"
    }}
  ]
}}"""

    def _parse_response(self, content: Any) -> list[dict[str, Any]]:
        """Parse model JSON response into normalized suggestion objects."""
        if not isinstance(content, str):
            content = str(content)

        cleaned = content.replace("```json", "").replace("```", "").strip()
        try:
            data = json.loads(cleaned)
        except Exception:
            return []

        raw_suggestions = data.get("suggestions")
        if not isinstance(raw_suggestions, list):
            legacy_corrections = data.get("corrections")
            if isinstance(legacy_corrections, list):
                raw_suggestions = [
                    {
                        "id": item.get("id"),
                        "suggestion": item.get("correction"),
                        "issue_type": "general",
                        "severity": "medium",
                        "rationale": "",
                    }
                    for item in legacy_corrections
                    if isinstance(item, dict)
                ]
            else:
                return []

        suggestions: list[dict[str, Any]] = []
        for item in raw_suggestions:
            if not isinstance(item, dict):
                continue
            raw_idx = item.get("id")
            suggestion = item.get("suggestion")
            try:
                idx = int(raw_idx)
            except (TypeError, ValueError):
                continue
            if isinstance(suggestion, str) and suggestion.strip():
                suggestions.append(
                    {
                        "id": idx,
                        "suggestion": suggestion.strip(),
                        "issue_type": str(item.get("issue_type") or "general"),
                        "severity": str(item.get("severity") or "medium"),
                        "rationale": str(item.get("rationale") or ""),
                    }
                )
        return suggestions
