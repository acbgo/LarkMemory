from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
import requests

from src.llm import openai_compatible_embedding_provider
from src.llm.openai_compatible_embedding_provider import OpenAICompatibleEmbeddingProvider


class FakeResponse:
    def __init__(self, *, status_code: int = 200, body: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._body = body or {
            "model": "Qwen/Qwen3-Embedding-4B",
            "data": [
                {"index": 0, "embedding": [0.1, 0.2, 0.3]},
                {"index": 1, "embedding": [0.4, 0.5, 0.6]},
            ],
            "usage": {"prompt_tokens": 7, "total_tokens": 7},
        }
        self.text = "response text"

    def json(self) -> dict[str, Any]:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


def test_openai_compatible_embedding_provider_sends_embedding_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, Any]] = []

    def fake_post(*args: Any, **kwargs: Any) -> FakeResponse:
        sent.append({"args": args, "kwargs": kwargs})
        return FakeResponse()

    monkeypatch.setattr(openai_compatible_embedding_provider.requests, "post", fake_post)

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

    request = sent[0]
    assert request["args"] == ("https://api.siliconflow.cn/v1/embeddings",)
    assert request["kwargs"]["headers"] == {
        "Authorization": "Bearer test-key",
        "Content-Type": "application/json",
    }
    assert request["kwargs"]["json"] == {
        "model": "Qwen/Qwen3-Embedding-4B",
        "input": ["alpha", "beta"],
        "encoding_format": "float",
        "dimensions": 1024,
    }
    assert request["kwargs"]["timeout"] == 30.0


def test_openai_compatible_embedding_provider_raises_for_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_post(*_args: Any, **_kwargs: Any) -> FakeResponse:
        return FakeResponse(status_code=502)

    monkeypatch.setattr(openai_compatible_embedding_provider.requests, "post", fake_post)

    provider = OpenAICompatibleEmbeddingProvider(
        api_key="test-key",
        model="Qwen/Qwen3-Embedding-4B",
        base_url="http://127.0.0.1:8001/v1",
    )

    with pytest.raises(requests.HTTPError):
        provider.embed_texts(["alpha"])


def test_openai_compatible_embedding_provider_requires_model() -> None:
    with pytest.raises(ValueError, match="Embedding model is required"):
        OpenAICompatibleEmbeddingProvider(api_key="test-key", model="")
