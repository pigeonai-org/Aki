"""
Qwen Provider Implementation

Uses DashScope SDK for Qwen models.
Currently provides Audio ASR support.
"""

import asyncio
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Optional, Union

from aki.models.base import ModelConfig, ModelResponse, ModelType
from aki.models.registry import ModelRegistry
from aki.models.types.audio import AudioModelInterface


@ModelRegistry.register("qwen", ModelType.AUDIO)
class QwenAudio(AudioModelInterface):
    """DashScope Qwen ASR implementation."""

    DASHSCOPE_INTL_BASE_URL = "https://dashscope-intl.aliyuncs.com/api/v1"
    DASHSCOPE_US_BASE_URL = "https://dashscope-us.aliyuncs.com/api/v1"
    MAX_RETRY_ATTEMPTS = 3

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self._dashscope = None

    def _get_client(self):
        """Lazy initialization of DashScope SDK module."""
        if self._dashscope is None:
            try:
                import dashscope
            except ImportError as exc:
                raise ImportError(
                    "dashscope package required. Install with: pip install dashscope"
                ) from exc
            self._dashscope = dashscope
        return self._dashscope

    async def transcribe(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> ModelResponse:
        """Transcribe audio using DashScope MultiModalConversation API."""
        dashscope = self._get_client()
        # Prefer explicitly configured key and only fallback to env when config is empty.
        api_key = self._normalize_api_key(
            self.config.api_key
            or os.environ.get("AKI_DASHSCOPE_API_KEY")
            or os.environ.get("DASHSCOPE_API_KEY")
        )
        if not api_key:
            raise ValueError("DashScope API key is required. Set AKI_DASHSCOPE_API_KEY.")

        asr_options = {"enable_lid": True, "enable_itn": False}
        extra_asr_options = kwargs.get("asr_options")
        if isinstance(extra_asr_options, dict):
            asr_options.update(extra_asr_options)
        if language:
            asr_options.setdefault("language", str(language).lower())

        model_name = self._normalize_model_name(self.config.model_name or "qwen3-asr-flash", None)
        explicit_base_url = self._resolve_base_url_override(dashscope)
        call_attempts = self._build_call_attempts(model_name, explicit_base_url)
        audio_ref, temp_path = self._to_audio_ref(audio)
        system_prompt = (prompt or "").strip()
        messages = self._build_messages(audio_ref, system_prompt)
        try:
            auth_failures: list[str] = []
            transport_failures: list[str] = []
            for attempt_base_url, attempt_model in call_attempts:
                self._configure_dashscope_base_url(dashscope, attempt_base_url)
                endpoint_label = attempt_base_url or "default"
                for retry_idx in range(self.MAX_RETRY_ATTEMPTS):
                    try:
                        response = dashscope.MultiModalConversation.call(
                            api_key=api_key,
                            model=attempt_model,
                            messages=messages,
                            result_format="message",
                            asr_options=asr_options,
                        )

                        text = self._extract_text(response) or ""
                        usage = self._extract_usage(response)

                        return ModelResponse(
                            content=text,
                            usage=usage or None,
                            model=attempt_model,
                            metadata={"language": language, "segments": []},
                        )
                    except Exception as exc:  # pragma: no cover - depends on remote SDK behavior
                        if self._is_retryable_transport_error(exc):
                            if retry_idx < self.MAX_RETRY_ATTEMPTS - 1:
                                await asyncio.sleep(0.2 * (retry_idx + 1))
                                continue
                            transport_failures.append(f"{endpoint_label} ({attempt_model}): {exc}")
                            break

                        mapped_exc = self._map_dashscope_error(exc)
                        if self._is_auth_error(mapped_exc):
                            auth_failures.append(f"{endpoint_label} ({attempt_model}): {exc}")
                            break
                        raise mapped_exc from exc

            if auth_failures:
                raise ValueError(
                    "DashScope authentication failed across all tried endpoints/models. "
                    "Check AKI_DASHSCOPE_API_KEY (or DASHSCOPE_API_KEY). "
                    "If your key is for international region, set "
                    "AKI_DASHSCOPE_BASE_URL=https://dashscope-intl.aliyuncs.com/api/v1; "
                    "for US region, set "
                    "AKI_DASHSCOPE_BASE_URL=https://dashscope-us.aliyuncs.com/api/v1. "
                    f"Attempts: {' | '.join(auth_failures)}"
                )
            if transport_failures:
                raise RuntimeError(
                    "DashScope request failed due to network/transport issues after retries. "
                    f"Attempts: {' | '.join(transport_failures)}"
                )
            raise RuntimeError("DashScope transcription failed without an explicit provider error.")
        finally:
            if temp_path:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except Exception:
                    pass

    @staticmethod
    def _normalize_api_key(api_key: Optional[str]) -> Optional[str]:
        """Normalize API key from env/user input."""
        if api_key is None:
            return None
        normalized = str(api_key).strip()
        if normalized.lower().startswith("bearer "):
            normalized = normalized[7:].strip()
        return normalized or None

    @staticmethod
    def _resolve_base_url_override(dashscope: Any) -> Optional[str]:
        """Resolve optional DashScope API base URL from environment/module config."""
        for env_key in (
            "AKI_DASHSCOPE_BASE_URL",
            "DASHSCOPE_BASE_URL",
            "DASHSCOPE_BASE_HTTP_API_URL",
        ):
            value = os.environ.get(env_key)
            if value and value.strip():
                return value.strip().rstrip("/")

        current = getattr(dashscope, "base_http_api_url", None)
        if isinstance(current, str) and current.strip():
            return current.strip().rstrip("/")
        return None

    @staticmethod
    def _configure_dashscope_base_url(dashscope: Any, base_url: Optional[str]) -> None:
        """Set DashScope API base URL when override is provided."""
        if base_url and base_url.strip():
            setattr(dashscope, "base_http_api_url", base_url.strip().rstrip("/"))

    def _build_call_attempts(
        self, model_name: str, base_url_override: Optional[str]
    ) -> list[tuple[Optional[str], str]]:
        """Build endpoint/model attempts for auth/region fallback."""
        base_candidates: list[Optional[str]] = []
        if base_url_override:
            base_candidates.append(base_url_override)
        else:
            base_candidates.append(None)

        for known_base in (self.DASHSCOPE_INTL_BASE_URL, self.DASHSCOPE_US_BASE_URL):
            if known_base not in base_candidates:
                base_candidates.append(known_base)

        attempts: list[tuple[Optional[str], str]] = []
        for base in base_candidates:
            normalized_model = self._normalize_model_name(model_name, base)
            attempts.append((base, normalized_model))

            alt_model = self._alternate_model_name(normalized_model)
            if alt_model:
                attempts.append((base, alt_model))

        seen: set[tuple[Optional[str], str]] = set()
        deduped_attempts: list[tuple[Optional[str], str]] = []
        for attempt in attempts:
            if attempt not in seen:
                seen.add(attempt)
                deduped_attempts.append(attempt)
        return deduped_attempts

    @staticmethod
    def _normalize_model_name(model_name: str, base_url: Optional[str]) -> str:
        """Normalize model aliases and region-specific model naming."""
        normalized = (model_name or "").strip() or "qwen3-asr-flash"
        if ":" in normalized:
            model_provider, compact_model = normalized.split(":", 1)
            if model_provider.strip().lower() == "qwen" and compact_model.strip():
                normalized = compact_model.strip()

        if (
            base_url
            and "dashscope-us.aliyuncs.com" in base_url.lower()
            and normalized.startswith("qwen3-asr-flash")
            and not normalized.endswith("-us")
        ):
            normalized = f"{normalized}-us"
        return normalized

    @staticmethod
    def _alternate_model_name(model_name: str) -> Optional[str]:
        """Build alternative model alias for region-mismatch retries."""
        normalized = (model_name or "").strip()
        if not normalized.startswith("qwen3-asr-flash"):
            return None
        if normalized.endswith("-us"):
            return normalized[: -len("-us")]
        return f"{normalized}-us"

    @staticmethod
    def _is_auth_error(exc: Exception) -> bool:
        """Return whether an exception message indicates authentication failure."""
        err_msg = str(exc).lower()
        auth_markers = (
            "invalidapikey",
            "invalid api-key",
            "invalid_api_key",
            "incorrect api key",
            "unauthorized",
            "forbidden",
            "access denied",
            "authentication",
            "401",
        )
        return any(marker in err_msg for marker in auth_markers)

    @staticmethod
    def _is_retryable_transport_error(exc: Exception) -> bool:
        """Return whether an exception likely represents transient transport failure."""
        err_msg = str(exc).lower()
        markers = (
            "httpsconnectionpool",
            "max retries exceeded",
            "sslerror",
            "unexpected eof while reading",
            "connection aborted",
            "connection reset",
            "timed out",
            "nodename nor servname provided",
            "name or service not known",
            "temporary failure in name resolution",
            "failed to resolve",
            "temporary failure",
        )
        return any(marker in err_msg for marker in markers)

    @staticmethod
    def _map_dashscope_error(exc: Exception) -> Exception:
        """Map low-level DashScope errors to actionable messages."""
        err_msg = str(exc)
        if QwenAudio._is_auth_error(exc):
            return ValueError(
                "DashScope authentication failed. Check AKI_DASHSCOPE_API_KEY "
                "(or DASHSCOPE_API_KEY) and ensure it is a valid DashScope key. "
                "If you are using a global/US DashScope key, set AKI_DASHSCOPE_BASE_URL "
                "(or DASHSCOPE_BASE_URL) to the matching endpoint. "
                f"Original error: {err_msg}"
            )
        return exc

    def _build_messages(self, audio_ref: str, system_prompt: str) -> list[dict[str, Any]]:
        """Build DashScope message payload following reference format."""
        return [
            {"role": "system", "content": [{"text": system_prompt}]},
            {"role": "user", "content": [{"audio": audio_ref}]},
        ]

    def _to_audio_ref(self, audio: Union[str, bytes]) -> tuple[str, Optional[str]]:
        """Convert local path/bytes/url audio to DashScope audio reference."""
        if isinstance(audio, bytes):
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio)
                tmp_path = tmp.name
            return str(Path(tmp_path).resolve().as_uri()), tmp_path

        if re.match(r"^https?://", str(audio), flags=re.IGNORECASE):
            return str(audio), None

        local_file = Path(audio).expanduser()
        if not local_file.exists():
            raise FileNotFoundError(f"Audio file not found: {audio}")
        return str(local_file.resolve().as_uri()), None

    def _extract_text(self, response: Any) -> Optional[str]:
        """Extract transcript text from DashScope response payload."""
        status_code = getattr(response, "status_code", None)
        if status_code is not None and int(status_code) >= 400:
            err = getattr(response, "message", None) or getattr(response, "code", None)
            raise RuntimeError(f"DashScope request failed ({status_code}): {err}")

        output = getattr(response, "output", None)
        if output is None and isinstance(response, dict):
            output = response.get("output")

        text_items: list[str] = []
        choices = None
        if output is not None:
            choices = getattr(output, "choices", None)
            if choices is None and isinstance(output, dict):
                choices = output.get("choices")

        for choice in choices or []:
            message = choice.get("message") if isinstance(choice, dict) else getattr(choice, "message", None)
            if not message:
                continue
            content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
            text_items.extend(self._extract_text_items(content))

        if not text_items:
            if output is not None:
                text_items.extend(self._extract_text_items(output))
            text_items.extend(self._extract_text_items(response))

        seen: set[str] = set()
        deduped_items: list[str] = []
        for item in text_items:
            if item and item not in seen:
                seen.add(item)
                deduped_items.append(item)

        merged_text = "\n".join(deduped_items).strip()
        return merged_text or None

    def _extract_text_items(self, payload: Any) -> list[str]:
        """Recursively extract text fields from nested payload structures."""
        if payload is None:
            return []
        if isinstance(payload, str):
            txt = payload.strip()
            return [txt] if txt else []
        if isinstance(payload, dict):
            collected: list[str] = []
            for key in ("text", "transcript", "asr_text", "value"):
                val = payload.get(key)
                if isinstance(val, str):
                    v = val.strip()
                    if v:
                        collected.append(v)
            for val in payload.values():
                collected.extend(self._extract_text_items(val))
            return collected
        if isinstance(payload, (list, tuple)):
            items: list[str] = []
            for item in payload:
                items.extend(self._extract_text_items(item))
            return items

        text_attr = getattr(payload, "text", None)
        if isinstance(text_attr, str):
            t = text_attr.strip()
            if t:
                return [t]
        if hasattr(payload, "__dict__"):
            return self._extract_text_items(vars(payload))
        return []

    def _extract_usage(self, response: Any) -> dict[str, int]:
        """Extract token usage from DashScope response if present."""
        usage = getattr(response, "usage", None)
        if usage is None and isinstance(response, dict):
            usage = response.get("usage")

        if usage is None:
            return {}

        if isinstance(usage, dict):
            prompt_tokens = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
            completion_tokens = usage.get("output_tokens") or usage.get("completion_tokens") or 0
            total_tokens = usage.get("total_tokens") or (prompt_tokens + completion_tokens)
            return {
                "prompt_tokens": int(prompt_tokens),
                "completion_tokens": int(completion_tokens),
                "total_tokens": int(total_tokens),
            }

        prompt_tokens = getattr(usage, "input_tokens", None) or getattr(usage, "prompt_tokens", 0)
        completion_tokens = getattr(usage, "output_tokens", None) or getattr(
            usage, "completion_tokens", 0
        )
        total_tokens = getattr(usage, "total_tokens", None) or (prompt_tokens + completion_tokens)
        return {
            "prompt_tokens": int(prompt_tokens or 0),
            "completion_tokens": int(completion_tokens or 0),
            "total_tokens": int(total_tokens or 0),
        }
