from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.llm import openai_compatible_embedding_provider
from src.llm.openai_compatible_embedding_provider import OpenAICompatibleEmbeddingProvider


class FakeEmbeddings:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        return SimpleNamespace(
            model="Qwen/Qwen3-Embedding-4B",
            data=[
                SimpleNamespace(index=0, embedding=[0.1, 0.2, 0.3]),
                SimpleNamespace(index=1, embedding=[0.4, 0.5, 0.6]),
            ],
            usage=SimpleNamespace(prompt_tokens=7, total_tokens=7),
        )


class FakeOpenAI:
    last_instance: "FakeOpenAI | None" = None

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.embeddings = FakeEmbeddings()
        FakeOpenAI.last_instance = self


def test_openai_compatible_embedding_provider_sends_embedding_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(openai_compatible_embedding_provider, "HAS_OPENAI", True)
    monkeypatch.setattr(openai_compatible_embedding_provider, "OpenAI", FakeOpenAI)

    provider = OpenAICompatibleEmbeddingProvider(
        api_key="test-key",
        model="Qwen/Qwen3-Embedding-4B",
        base_url="https://api.siliconflow.cn/v1",
        dimensions=1024,
        encoding_format="float",
        timeout=30.0,
        max_retries=1,
    )

    response = provider.embed_texts(["alpha", "beta"])

    assert response.model == "Qwen/Qwen3-Embedding-4B"
    assert response.embeddings == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    assert response.dimensions == 3
    assert response.usage == {"prompt_tokens": 7, "total_tokens": 7}

    fake_client = FakeOpenAI.last_instance
    assert fake_client is not None
    assert fake_client.kwargs["api_key"] == "test-key"
    assert fake_client.kwargs["base_url"] == "https://api.siliconflow.cn/v1"
    assert fake_client.kwargs["timeout"] == 30.0
    assert fake_client.kwargs["max_retries"] == 1

    request = fake_client.embeddings.requests[0]
    assert request == {
        "model": "Qwen/Qwen3-Embedding-4B",
        "input": ["alpha", "beta"],
        "encoding_format": "float",
        "dimensions": 1024,
    }


def test_openai_compatible_embedding_provider_requires_model() -> None:
    with pytest.raises(ValueError, match="Embedding model is required"):
        OpenAICompatibleEmbeddingProvider(api_key="test-key", model="")
