from __future__ import annotations

import json
import logging
from typing import Any
from urllib import request

from .rerank_base import RerankScore

logger = logging.getLogger(__name__)


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
        _log_response_shape(data)
        return _parse_scores(data)


def _parse_scores(data: Any) -> list[RerankScore]:
    """Parse common rerank response shapes into indexed scores."""
    if isinstance(data, list):
        results = data
    elif not isinstance(data, dict):
        return []
    else:
        if "error" in data:
            raise RuntimeError(f"Rerank provider returned error: {data.get('error')}")
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
        score = _extract_score(item)
        scores.append(RerankScore(index=index, score=score))
    return scores


def _extract_score(item: dict[str, Any]) -> float:
    """Read the first supported score field from a rerank result object."""

    for key in ("score", "relevance_score", "similarity", "logit"):
        if key in item:
            return float(item[key])
    return 0.0


def _log_response_shape(data: Any) -> None:
    """Log compact rerank response diagnostics without document text."""

    if isinstance(data, dict):
        results = data.get("results") or data.get("data") or []
        preview = results[:3] if isinstance(results, list) else []
        logger.info(
            "action=http_rerank_response_received keys=%s result_count=%s preview=%s",
            sorted(data.keys()),
            len(results) if isinstance(results, list) else 0,
            [_compact_result(item) for item in preview if isinstance(item, dict)],
        )
        return
    if isinstance(data, list):
        logger.info(
            "action=http_rerank_response_received keys=[] result_count=%s preview=%s",
            len(data),
            [_compact_result(item) for item in data[:3] if isinstance(item, dict)],
        )
        return
    logger.info(
        "action=http_rerank_response_received keys=[] result_count=0 raw_type=%s",
        type(data).__name__,
    )


def _compact_result(item: dict[str, Any]) -> dict[str, Any]:
    """Keep only routing and score fields from a provider result."""

    return {
        key: item.get(key)
        for key in ("id", "index", "score", "relevance_score", "similarity", "logit")
        if key in item
    }
