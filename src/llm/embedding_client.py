from __future__ import annotations

from .embedding_base import EmbeddingProvider, EmbeddingResponse


class EmbeddingClient:
    """Validate embedding inputs and delegate vector generation to a provider."""

    def __init__(self, provider: EmbeddingProvider) -> None:
        self.provider = provider

    def embed_text(self, text: str) -> list[float]:
        """Embed one text string and return its vector."""
        return self.embed_texts([text]).embeddings[0]

    def embed_texts(self, texts: list[str]) -> EmbeddingResponse:
        """Embed a batch of non-blank text strings."""
        if not texts:
            return EmbeddingResponse(model="", embeddings=[], dimensions=0)
        cleaned = [text.strip() for text in texts]
        if any(not text for text in cleaned):
            raise ValueError("embedding input text cannot be empty")
        return self.provider.embed_texts(cleaned)
