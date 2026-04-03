"""Subtitle editing tool."""

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
class SubtitleEditTool(BaseTool):
    """Final style and coherence pass for subtitle entries."""

    name = "subtitle_edit"
    description = "Edit subtitles for coherence and style"
    parameters = [
        ToolParameter(
            name="subtitles",
            type="array",
            description="List of subtitle entries",
        ),
    ]

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
        subtitles: list[dict[str, Any]],
        domain: str = "general",
        instructions: Optional[str] = None,
        context_window: int = 3,
        suggestions: Optional[list[dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute subtitle editing."""
        if context_window < 0:
            return ToolResult.fail("context_window must be >= 0")

        try:
            entries = [SubtitleEntry(**s) for s in subtitles]
            edited_entries = await self._edit_all(
                entries=entries,
                domain=domain,
                instructions=instructions,
                window=context_window,
                suggestions_by_id=self._group_suggestions_by_id(suggestions or []),
            )

            return ToolResult.ok(
                data={
                    "subtitles": [entry.model_dump() for entry in edited_entries],
                    "count": len(edited_entries),
                    "applied_suggestions": len(suggestions or []),
                }
            )
        except Exception as e:
            return ToolResult.fail(f"Editing failed: {str(e)}")

    async def _edit_all(
        self,
        entries: list[SubtitleEntry],
        domain: str,
        instructions: Optional[str],
        window: int,
        suggestions_by_id: dict[int, list[str]],
    ) -> list[SubtitleEntry]:
        """Edit all entries with sliding-window translation context."""
        model = self._get_model()
        updated_entries: list[SubtitleEntry] = []

        for idx, entry in enumerate(entries):
            start = max(0, idx - window)
            end = min(len(entries), idx + window + 1)
            prev_context = entries[start:idx]
            next_context = entries[idx + 1 : end]
            current_suggestions = suggestions_by_id.get(entry.index, [])

            prompt = self._build_prompt(
                current=entry,
                prev_ctx=prev_context,
                next_ctx=next_context,
                domain=domain,
                instructions=instructions,
                reviewer_suggestions=current_suggestions,
            )

            try:
                response = await model.chat(
                    messages=[
                        {"role": "system", "content": "You are a professional subtitle editor."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.0,
                )
                revised = self._extract_response_text(response.content).strip()
                if revised:
                    entry.translation = revised
            except Exception:
                pass

            updated_entries.append(entry)

        return updated_entries

    @staticmethod
    def _extract_response_text(content: Any) -> str:
        """Extract plain text from model response content."""
        if isinstance(content, str):
            return content
        if isinstance(content, dict) and isinstance(content.get("text"), str):
            return content["text"]
        return str(content)

    def _build_prompt(
        self,
        current: SubtitleEntry,
        prev_ctx: list[SubtitleEntry],
        next_ctx: list[SubtitleEntry],
        domain: str,
        instructions: Optional[str],
        reviewer_suggestions: list[str],
    ) -> str:
        prev_str = (
            "\n".join(
                (entry.translation or entry.text).strip()
                for entry in prev_ctx
                if (entry.translation or entry.text).strip()
            )
            or "None"
        )
        next_str = (
            "\n".join(
                (entry.translation or entry.text).strip()
                for entry in next_ctx
                if (entry.translation or entry.text).strip()
            )
            or "None"
        )
        suggestions_text = "\n".join(f"- {item}" for item in reviewer_suggestions) or "None"

        return f"""Edit the following subtitle segment for flow, style, and domain consistency.
Domain: {domain}
Instructions: {instructions or "Ensure natural flow and correct terminology."}

Context (Previous):
{prev_str}

Context (Next):
{next_str}

Reviewer Suggestions:
{suggestions_text}

Current Segment:
Source: {current.src_text or current.text}
Translation: {current.translation or current.text}

Output ONLY the revised translation. If no change is needed, output the current translation."""

    @staticmethod
    def _group_suggestions_by_id(suggestions: list[dict[str, Any]]) -> dict[int, list[str]]:
        """Group suggestion strings by subtitle index."""
        grouped: dict[int, list[str]] = {}
        for item in suggestions:
            if not isinstance(item, dict):
                continue
            raw_id = item.get("id")
            suggestion = str(item.get("suggestion") or "").strip()
            try:
                idx = int(raw_id)
            except (TypeError, ValueError):
                continue
            if not suggestion:
                continue
            grouped.setdefault(idx, []).append(suggestion)
        return grouped
