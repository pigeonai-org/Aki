"""Model type interfaces."""

from aki.models.types.audio import AudioModelInterface
from aki.models.types.embedding import EmbeddingModelInterface
from aki.models.types.llm import LLMInterface
from aki.models.types.vlm import VLMInterface

__all__ = [
    "LLMInterface",
    "VLMInterface",
    "AudioModelInterface",
    "EmbeddingModelInterface",
]
