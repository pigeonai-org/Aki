"""Subtitle translation tool."""

from copy import deepcopy
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
class SubtitleTranslateTool(BaseTool):
    """Translate SRT entries with optional context and post-split."""

    name = "subtitle_translate"
    description = "Translate subtitles with context and optional long-line splitting"
    parameters = [
        ToolParameter(
            name="subtitles",
            type="array",
            description="List of subtitle entries (from srt_read)",
        ),
        ToolParameter(
            name="source_language",
            type="string",
            description="Source language code (e.g., 'en')",
        ),
        ToolParameter(
            name="target_language",
            type="string",
            description="Target language code (e.g., 'zh')",
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
        self.translation_history: list[str] = []

    def _get_model(self) -> LLMInterface:
        if self._llm_model is None:
            self._llm_model = ModelRegistry.get(self._model_config, ModelType.LLM)
        return self._llm_model

    @staticmethod
    def _seconds_to_srt(seconds: float) -> str:
        """Convert seconds to HH:MM:SS,mmm."""
        total_ms = max(0, int(round(float(seconds) * 1000)))
        ms = total_ms % 1000
        total_s = total_ms // 1000
        s = total_s % 60
        total_m = total_s // 60
        m = total_m % 60
        h = total_m // 60
        return f"{h:02}:{m:02}:{s:02},{ms:03}"

    @staticmethod
    def _normalize_subtitle_payload(
        subtitles: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Normalize subtitle entries to satisfy SubtitleEntry schema."""
        normalized: list[dict[str, Any]] = []

        for idx, subtitle in enumerate(subtitles, start=1):
            if not isinstance(subtitle, dict):
                continue

            item = dict(subtitle)
            source_text = str(
                item.get("src_text") or item.get("text") or item.get("translation") or ""
            ).strip()
            if not source_text:
                continue

            start_time = item.get("start_time")
            if not start_time:
                try:
                    start_time = SubtitleTranslateTool._seconds_to_srt(
                        float(item.get("start_seconds") or 0.0)
                    )
                except Exception:
                    start_time = "00:00:00,000"

            end_time = item.get("end_time")
            if not end_time:
                try:
                    end_val = item.get("end_seconds")
                    if end_val is None:
                        end_val = float(item.get("start_seconds") or 0.0) + 1.0
                    end_time = SubtitleTranslateTool._seconds_to_srt(float(end_val))
                except Exception:
                    end_time = "00:00:01,000"

            entry_index = item.get("index")
            if isinstance(entry_index, str) and entry_index.isdigit():
                entry_index = int(entry_index)
            if not isinstance(entry_index, int) or entry_index <= 0:
                entry_index = idx

            normalized.append(
                {
                    **item,
                    "index": entry_index,
                    "start_time": str(start_time),
                    "end_time": str(end_time),
                    "text": source_text,
                    "src_text": str(item.get("src_text") or source_text),
                }
            )

        return normalized

    async def execute(
        self,
        subtitles: list[dict[str, Any]],
        source_language: str,
        target_language: str,
        domain: str = "general",
        batch_size: int = 5,
        split_threshold: int = 80,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute subtitle translation."""
        if batch_size < 1:
            return ToolResult.fail("batch_size must be >= 1")
        if split_threshold < 1:
            return ToolResult.fail("split_threshold must be >= 1")

        try:
            normalized_subtitles = self._normalize_subtitle_payload(subtitles)
            if not normalized_subtitles:
                return ToolResult.fail("Subtitle translation failed: no valid subtitle entries provided.")

            entries = [SubtitleEntry(**s) for s in normalized_subtitles]
            self.translation_history = []

            translated_entries = await self._translate_all(
                entries=entries,
                src_lang=source_language,
                tgt_lang=target_language,
                domain=domain,
            )

            final_entries = self._post_process_split(
                entries=translated_entries,
                split_threshold=split_threshold,
            )

            return ToolResult.ok(
                data={
                    "subtitles": [s.model_dump() for s in final_entries],
                    "count": len(final_entries),
                }
            )
        except Exception as e:
            return ToolResult.fail(f"Subtitle translation failed: {str(e)}")

    async def _translate_all(
        self,
        entries: list[SubtitleEntry],
        src_lang: str,
        tgt_lang: str,
        domain: str,
    ) -> list[SubtitleEntry]:
        """Translate entries sequentially to preserve history context."""
        model = self._get_model()
        updated_entries: list[SubtitleEntry] = []

        for entry in entries:
            source_text = (entry.src_text or entry.text).strip()
            if not source_text:
                entry.translation = ""
                updated_entries.append(entry)
                continue

            history = "\n".join(self.translation_history[-5:])
            context_str = await self._build_rag_context(source_text)
            prompt = self._build_prompt(
                text=source_text,
                src=src_lang,
                tgt=tgt_lang,
                domain=domain,
                history=history,
                context=context_str,
            )

            try:
                response = await model.chat(
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a professional subtitle translator.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                )
                translation = self._extract_response_text(response.content).strip()
            except Exception:
                translation = ""

            entry.src_text = source_text
            entry.translation = translation
            if translation:
                self.translation_history.append(translation)
            updated_entries.append(entry)

        return updated_entries

    async def _build_rag_context(self, query: str) -> str:
        """Build context text from optional RAG results."""
        if self.rag is None:
            return ""

        try:
            results = await self.rag.search(query, limit=3)
        except Exception:
            return ""

        context_parts: list[str] = []
        for result in results:
            item = getattr(result, "item", None)
            if item is not None and getattr(item, "content", None):
                context_parts.append(str(item.content))
            else:
                context_parts.append(str(result))
        return "\n".join(context_parts)

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
        text: str,
        src: str,
        tgt: str,
        domain: str,
        history: str,
        context: str,
    ) -> str:
        history_block = history if history else "None"
        context_block = context if context else "None"
        return f"""Translate the following subtitle from {src} to {tgt}.
Domain: {domain}

Context (Previous translations):
{history_block}

Additional Context:
{context_block}

Subtitle to translate:
{text}

Output only the translation, no extra text."""

    def _post_process_split(
        self,
        entries: list[SubtitleEntry],
        split_threshold: int,
    ) -> list[SubtitleEntry]:
        """Split overly long translated lines into shorter entries."""
        final_list: list[SubtitleEntry] = []
        for entry in entries:
            if entry.translation and len(entry.translation) > split_threshold:
                final_list.extend(self._split_segment(entry))
            else:
                final_list.append(entry)

        for idx, result_entry in enumerate(final_list, 1):
            result_entry.index = idx
        return final_list

    def _split_segment(self, entry: SubtitleEntry) -> list[SubtitleEntry]:
        """Split one entry around nearest punctuation close to midpoint."""
        if not entry.translation:
            return [entry]

        text = entry.translation
        mid = len(text) // 2
        split_idx = mid
        best_dist = mid

        for idx, char in enumerate(text):
            if char in " ,.?!，。？！":
                dist = abs(idx - mid)
                if dist < best_dist:
                    best_dist = dist
                    split_idx = idx

        part1_text = text[: split_idx + 1].strip()
        part2_text = text[split_idx + 1 :].strip()
        if not part1_text or not part2_text:
            return [entry]

        try:
            start = self._parse_time(entry.start_time)
            end = self._parse_time(entry.end_time)
            duration = max(0.0, end - start)
            ratio = len(part1_text) / max(1, len(text))
            mid_time = start + duration * ratio

            part1 = deepcopy(entry)
            part1.translation = part1_text
            part1.end_time = self._format_time(mid_time)

            part2 = deepcopy(entry)
            part2.translation = part2_text
            part2.start_time = self._format_time(mid_time)
            return [part1, part2]
        except Exception:
            return [entry]

    @staticmethod
    def _parse_time(time_str: str) -> float:
        """Parse HH:MM:SS,mmm or HH:MM:SS.mmm into seconds."""
        normalized = time_str.replace(".", ",")
        h_str, m_str, s_ms_str = normalized.split(":")
        s_str, ms_str = s_ms_str.split(",")
        return int(h_str) * 3600 + int(m_str) * 60 + int(s_str) + int(ms_str) / 1000.0

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds into HH:MM:SS,mmm."""
        total_ms = max(0, int(round(seconds * 1000)))
        ms = total_ms % 1000
        total_s = total_ms // 1000
        s = total_s % 60
        total_m = total_s // 60
        m = total_m % 60
        h = total_m // 60
        return f"{h:02}:{m:02}:{s:02},{ms:03}"
