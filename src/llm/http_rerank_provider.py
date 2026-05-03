from __future__ import annotations

import json
from typing import Any
from urllib import request

from .rerank_base import RerankScore


class HttpRerankProvider:
    """HTTP adapter for a deployed rerank model service."""

    def __init__(
        self,
        *,
        base_url: str,
        endpoint_path: str = "/rerank",
        model: str | None = None,
        api_key: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        if not base_url:
            raise ValueError("Rerank base URL is required")
        self.base_url = base_url.rstrip("/")
        self.endpoint_path = endpoint_path if endpoint_path.startswith("/") else f"/{endpoint_path}"
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def score(self, query: str, documents: list[str]) -> list[RerankScore]:
        """POST query/documents to the rerank service and parse score results."""
        payload: dict[str, Any] = {
            "query": query,
            "documents": documents,
        }
        if self.model:
            payload["model"] = self.model
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = request.Request(
            f"{self.base_url}{self.endpoint_path}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with request.urlopen(req, timeout=self.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        return _parse_scores(data)


def _parse_scores(data: dict[str, Any]) -> list[RerankScore]:
    """Parse common rerank response shapes into indexed scores."""
    if isinstance(data.get("scores"), list):
        return [
            RerankScore(index=index, score=float(score))
            for index, score in enumerate(data["scores"])
        ]
    results = data.get("results") or data.get("data") or []
    scores: list[RerankScore] = []
    for fallback_index, item in enumerate(results):
        if not isinstance(item, dict):
            continue
        index = int(item.get("index", fallback_index))
        score = float(item.get("score", item.get("relevance_score", 0.0)))
        scores.append(RerankScore(index=index, score=score))
    return scores
