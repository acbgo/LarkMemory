from __future__ import annotations

import json
from io import BytesIO
from typing import Any

import pytest

from src.llm import http_rerank_provider
from src.llm.http_rerank_provider import HttpRerankProvider


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_http_rerank_provider_posts_query_and_documents(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[Any] = []

    def fake_urlopen(request: Any, timeout: float) -> FakeHTTPResponse:
        requests.append((request, timeout))
        return FakeHTTPResponse(
            {
                "results": [
                    {"index": 0, "score": 0.1},
                    {"index": 1, "score": 0.8},
                ]
            }
        )

    monkeypatch.setattr(http_rerank_provider.request, "urlopen", fake_urlopen)

    provider = HttpRerankProvider(
        base_url="http://127.0.0.1:9000",
        endpoint_path="/rerank",
        model="bge-reranker",
        api_key="test-key",
        timeout=3.0,
    )

    scores = provider.score("query", ["doc-a", "doc-b"])

    assert [(score.index, score.score) for score in scores] == [(0, 0.1), (1, 0.8)]
    req, timeout = requests[0]
    assert timeout == 3.0
    assert req.full_url == "http://127.0.0.1:9000/rerank"
    assert req.headers["Authorization"] == "Bearer test-key"
    payload = json.loads(req.data.decode("utf-8"))
    assert payload == {
        "model": "bge-reranker",
        "query": "query",
        "documents": ["doc-a", "doc-b"],
    }


def test_http_rerank_provider_accepts_scores_response(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: Any, timeout: float) -> FakeHTTPResponse:
        return FakeHTTPResponse({"scores": [0.3, 0.7]})

    monkeypatch.setattr(http_rerank_provider.request, "urlopen", fake_urlopen)
    provider = HttpRerankProvider(base_url="http://127.0.0.1:9000")

    scores = provider.score("query", ["doc-a", "doc-b"])

    assert [(score.index, score.score) for score in scores] == [(0, 0.3), (1, 0.7)]


def test_http_rerank_provider_requires_base_url() -> None:
    with pytest.raises(ValueError, match="Rerank base URL is required"):
        HttpRerankProvider(base_url="")
