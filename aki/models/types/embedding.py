"""
Embedding Model Interface

Interface for text embedding models.
"""

from abc import abstractmethod
from typing import Any, Union

from aki.models.base import BaseModelInterface, ModelResponse, ModelType


class EmbeddingModelInterface(BaseModelInterface):
    """
    Embedding Model Interface for text vectorization.

    Converts text to vector embeddings for semantic search.
    """

    model_type = ModelType.EMBEDDING

    @abstractmethod
    async def embed(
        self,
        texts: Union[str, list[str]],
        **kwargs: Any,
    ) -> ModelResponse:
        """
        Generate embeddings for text(s).

        Args:
            texts: Single text or list of texts to embed
            **kwargs: Additional model-specific parameters

        Returns:
            ModelResponse with embeddings (list of float vectors)
        """
        pass

    async def invoke(self, **kwargs: Any) -> ModelResponse:
        """Invoke the model using embed interface."""
        texts = kwargs.pop("texts", "")
        return await self.embed(texts, **kwargs)

    async def stream(self, **kwargs: Any):
        """Stream is not implemented for embedding models."""
        raise NotImplementedError("Streaming not implemented for embedding models")
