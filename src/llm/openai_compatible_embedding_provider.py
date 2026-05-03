from __future__ import annotations

from typing import Any

from .embedding_base import EmbeddingResponse

try:
    from openai import OpenAI

    HAS_OPENAI = True
except ImportError:
    OpenAI = None  # type: ignore[assignment]
    HAS_OPENAI = False


class OpenAICompatibleEmbeddingProvider:
    """Synchronous OpenAI-compatible embeddings provider for API services."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str | None = None,
        dimensions: int | None = None,
        encoding_format: str = "float",
        timeout: float = 60.0,
        max_retries: int = 2,
    ) -> None:
        if not model:
            raise ValueError("Embedding model is required")
        if not api_key:
            raise ValueError("Embedding API key is required")
        if not HAS_OPENAI:
            raise ImportError("Missing dependency: openai")
        self.model = model
        self.dimensions = dimensions
        self.encoding_format = encoding_format
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )

    def embed_texts(self, texts: list[str]) -> EmbeddingResponse:
        """Call `/embeddings` and return vectors in the same order as input."""
        request: dict[str, Any] = {
            "model": self.model,
            "input": texts,
            "encoding_format": self.encoding_format,
        }
        if self.dimensions is not None:
            request["dimensions"] = self.dimensions
        response = self._client.embeddings.create(**request)
        embeddings = [list(item.embedding) for item in response.data]
        usage = _usage_to_dict(getattr(response, "usage", None))
        return EmbeddingResponse(
            model=getattr(response, "model", None) or self.model,
            embeddings=embeddings,
            dimensions=len(embeddings[0]) if embeddings else 0,
            usage=usage,
        )


def _usage_to_dict(usage: Any | None) -> dict[str, int] | None:
    """Normalize OpenAI SDK usage objects into plain dictionaries."""
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        return dict(usage.model_dump())
    result: dict[str, int] = {}
    for key in ("prompt_tokens", "total_tokens"):
        value = getattr(usage, key, None)
        if isinstance(value, int):
            result[key] = value
    return result or None
