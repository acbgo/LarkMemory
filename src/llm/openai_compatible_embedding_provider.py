from __future__ import annotations

from typing import Any

import requests

from .embedding_base import EmbeddingResponse


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
        self.api_key = api_key
        self.model = model
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.dimensions = dimensions
        self.encoding_format = encoding_format
        self.timeout = timeout
        self.max_retries = max_retries

    def embed_texts(self, texts: list[str]) -> EmbeddingResponse:
        """Call `/embeddings` and return vectors in the same order as input."""
        request: dict[str, Any] = {
            "model": self.model,
            "input": texts,
            "encoding_format": self.encoding_format,
        }
        if self.dimensions is not None:
            request["dimensions"] = self.dimensions
        response = requests.post(
            f"{self.base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=request,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", [])
        embeddings = [list(item["embedding"]) for item in data]
        usage = _usage_to_dict(payload.get("usage"))
        return EmbeddingResponse(
            model=payload.get("model") or self.model,
            embeddings=embeddings,
            dimensions=len(embeddings[0]) if embeddings else 0,
            usage=usage,
        )


def _usage_to_dict(usage: Any | None) -> dict[str, int] | None:
    """Normalize OpenAI SDK usage objects into plain dictionaries."""
    if usage is None:
        return None
    if isinstance(usage, dict):
        return {
            key: value
            for key in ("prompt_tokens", "total_tokens")
            if isinstance((value := usage.get(key)), int)
        } or None
    if hasattr(usage, "model_dump"):
        return dict(usage.model_dump())
    result: dict[str, int] = {}
    for key in ("prompt_tokens", "total_tokens"):
        value = getattr(usage, key, None)
        if isinstance(value, int):
            result[key] = value
    return result or None
