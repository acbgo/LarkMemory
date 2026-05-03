from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class EmbeddingResponse:
    """Embedding model response shared by API and local providers."""

    model: str
    embeddings: list[list[float]]
    dimensions: int
    usage: dict[str, int] | None = None


class EmbeddingProvider(Protocol):
    """Provider contract for text embedding backends."""

    def embed_texts(self, texts: list[str]) -> EmbeddingResponse:
        """Return embeddings for a non-empty batch of texts."""
        ...
