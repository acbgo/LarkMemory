from __future__ import annotations

from typing import Any

import pytest

from src.llm import local_sentence_transformers_embedding_provider
from src.llm.local_sentence_transformers_embedding_provider import (
    LocalSentenceTransformersEmbeddingProvider,
)


class FakeVectorList(list):
    def tolist(self) -> list[list[float]]:
        return list(self)


class FakeSentenceTransformer:
    last_instance: "FakeSentenceTransformer | None" = None

    def __init__(self, model_name_or_path: str, **kwargs: Any) -> None:
        self.model_name_or_path = model_name_or_path
        self.kwargs = kwargs
        self.encode_calls: list[dict[str, Any]] = []
        FakeSentenceTransformer.last_instance = self

    def encode(self, texts: list[str], **kwargs: Any) -> FakeVectorList:
        self.encode_calls.append({"texts": texts, "kwargs": kwargs})
        return FakeVectorList(
            [
                [0.1, 0.2, 0.3, 0.4],
                [0.5, 0.6, 0.7, 0.8],
            ][: len(texts)]
        )


def test_local_sentence_transformers_provider_loads_model_and_encodes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(local_sentence_transformers_embedding_provider, "HAS_SENTENCE_TRANSFORMERS", True)
    monkeypatch.setattr(
        local_sentence_transformers_embedding_provider,
        "SentenceTransformer",
        FakeSentenceTransformer,
    )

    provider = LocalSentenceTransformersEmbeddingProvider(
        model_path=".larkmemory/models/Qwen/Qwen3-Embedding-4B",
        device="cpu",
        normalize_embeddings=True,
        batch_size=4,
        trust_remote_code=True,
        dimensions=2,
    )

    response = provider.embed_texts(["alpha", "beta"])

    assert response.model == ".larkmemory/models/Qwen/Qwen3-Embedding-4B"
    assert response.embeddings == [[0.1, 0.2], [0.5, 0.6]]
    assert response.dimensions == 2
    assert response.usage is None

    fake_model = FakeSentenceTransformer.last_instance
    assert fake_model is not None
    assert fake_model.model_name_or_path == ".larkmemory/models/Qwen/Qwen3-Embedding-4B"
    assert fake_model.kwargs["device"] == "cpu"
    assert fake_model.kwargs["trust_remote_code"] is True
    assert fake_model.encode_calls[0]["texts"] == ["alpha", "beta"]
    assert fake_model.encode_calls[0]["kwargs"]["batch_size"] == 4
    assert fake_model.encode_calls[0]["kwargs"]["normalize_embeddings"] is True


def test_local_sentence_transformers_provider_requires_model_path() -> None:
    with pytest.raises(ValueError, match="Local embedding model path is required"):
        LocalSentenceTransformersEmbeddingProvider(model_path="")


def test_local_sentence_transformers_provider_reports_missing_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(local_sentence_transformers_embedding_provider, "HAS_SENTENCE_TRANSFORMERS", False)

    with pytest.raises(ImportError, match="sentence-transformers"):
        LocalSentenceTransformersEmbeddingProvider(model_path=".larkmemory/models/Qwen/Qwen3-Embedding-4B")
