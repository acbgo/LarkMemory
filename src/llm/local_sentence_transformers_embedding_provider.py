from __future__ import annotations

from typing import Any

from .embedding_base import EmbeddingResponse

try:
    from sentence_transformers import SentenceTransformer

    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    SentenceTransformer = None  # type: ignore[assignment]
    HAS_SENTENCE_TRANSFORMERS = False


class LocalSentenceTransformersEmbeddingProvider:
    """Load a local SentenceTransformers-compatible embedding model."""

    def __init__(
        self,
        *,
        model_path: str,
        device: str = "cpu",
        normalize_embeddings: bool = True,
        batch_size: int = 4,
        dimensions: int | None = None,
        trust_remote_code: bool = True,
    ) -> None:
        if not model_path:
            raise ValueError("Local embedding model path is required")
        if not HAS_SENTENCE_TRANSFORMERS:
            raise ImportError("Missing dependency: sentence-transformers")
        self.model_path = model_path
        self.normalize_embeddings = normalize_embeddings
        self.batch_size = batch_size
        self.dimensions = dimensions
        self._model = SentenceTransformer(
            model_path,
            device=device,
            trust_remote_code=trust_remote_code,
        )

    def embed_texts(self, texts: list[str]) -> EmbeddingResponse:
        """Encode text batch with the local model and return plain Python vectors."""
        vectors = self._model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=self.normalize_embeddings,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        embeddings = _vectors_to_lists(vectors)
        if self.dimensions is not None:
            embeddings = [vector[: self.dimensions] for vector in embeddings]
        return EmbeddingResponse(
            model=self.model_path,
            embeddings=embeddings,
            dimensions=len(embeddings[0]) if embeddings else 0,
            usage=None,
        )


def _vectors_to_lists(vectors: Any) -> list[list[float]]:
    """Convert numpy/list vector outputs into `list[list[float]]`."""
    raw = vectors.tolist() if hasattr(vectors, "tolist") else vectors
    return [[float(value) for value in vector] for vector in raw]
