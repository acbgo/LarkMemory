from __future__ import annotations

import pytest

from src.llm.rerank_base import RerankDocument, RerankScore
from src.llm.rerank_client import RerankClient


class FakeRerankProvider:
    def __init__(self, scores: list[float]) -> None:
        self.scores = scores
        self.calls: list[dict[str, object]] = []

    def score(self, query: str, documents: list[str]) -> list[RerankScore]:
        self.calls.append({"query": query, "documents": documents})
        return [RerankScore(index=index, score=score) for index, score in enumerate(self.scores)]


def test_rerank_client_sorts_documents_by_provider_score() -> None:
    provider = FakeRerankProvider([0.2, 0.9, 0.5])
    client = RerankClient(provider, model_name="server-reranker")

    response = client.rerank(
        "客户 A 导出格式",
        [
            RerankDocument(id="mem-1", text="客户 B 偏好 PDF"),
            RerankDocument(id="mem-2", text="客户 A 要求 xlsx"),
            RerankDocument(id="mem-3", text="客户 A 的会议纪要"),
        ],
        top_k=2,
    )

    assert response.model == "server-reranker"
    assert [item.id for item in response.results] == ["mem-2", "mem-3"]
    assert [item.rank for item in response.results] == [1, 2]
    assert response.results[0].score == 0.9
    assert provider.calls == [
        {
            "query": "客户 A 导出格式",
            "documents": ["客户 B 偏好 PDF", "客户 A 要求 xlsx", "客户 A 的会议纪要"],
        }
    ]


def test_rerank_client_rejects_blank_query() -> None:
    client = RerankClient(FakeRerankProvider([]))

    with pytest.raises(ValueError, match="query cannot be empty"):
        client.rerank("   ", [RerankDocument(id="mem-1", text="text")])


def test_rerank_client_returns_empty_result_for_empty_documents() -> None:
    client = RerankClient(FakeRerankProvider([]), model_name="fake")

    response = client.rerank("query", [])

    assert response.model == "fake"
    assert response.results == []
