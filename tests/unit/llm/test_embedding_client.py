from __future__ import annotations

import pytest

from src.llm.embedding_base import EmbeddingResponse
from src.llm.embedding_client import EmbeddingClient


class FakeEmbeddingProvider:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_texts(self, texts: list[str]) -> EmbeddingResponse:
        self.calls.append(texts)
        return EmbeddingResponse(
            model="fake-embedding",
            embeddings=[[float(index), 1.0] for index, _ in enumerate(texts)],
            dimensions=2,
            usage={"prompt_tokens": 3, "total_tokens": 3},
        )


def test_embedding_client_embeds_single_text() -> None:
    provider = FakeEmbeddingProvider()
    client = EmbeddingClient(provider)

    vector = client.embed_text("  project memory  ")

    assert vector == [0.0, 1.0]
    assert provider.calls == [["project memory"]]


def test_embedding_client_rejects_empty_text() -> None:
    client = EmbeddingClient(FakeEmbeddingProvider())

    with pytest.raises(ValueError, match="cannot be empty"):
        client.embed_text("   ")


def test_embedding_client_returns_empty_response_for_empty_batch() -> None:
    client = EmbeddingClient(FakeEmbeddingProvider())

    response = client.embed_texts([])

    assert response.embeddings == []
    assert response.dimensions == 0
