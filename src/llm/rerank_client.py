from __future__ import annotations

from .rerank_base import RerankDocument, RerankProvider, RerankResponse, RerankResult


class RerankClient:
    """Validate rerank inputs and sort documents by provider scores."""

    def __init__(self, provider: RerankProvider, *, model_name: str = "") -> None:
        self.provider = provider
        self.model_name = model_name

    def rerank(
        self,
        query: str,
        documents: list[RerankDocument],
        *,
        top_k: int | None = None,
    ) -> RerankResponse:
        """Return documents ranked by relevance to the query."""
        cleaned_query = query.strip()
        if not cleaned_query:
            raise ValueError("rerank query cannot be empty")
        if not documents:
            return RerankResponse(model=self.model_name, results=[])
        scores = self.provider.score(cleaned_query, [item.text for item in documents])
        score_by_index = {score.index: score.score for score in scores}
        ranked = sorted(
            enumerate(documents),
            key=lambda item: score_by_index.get(item[0], float("-inf")),
            reverse=True,
        )
        limit = top_k if top_k is not None else len(ranked)
        results = [
            RerankResult(
                id=document.id,
                text=document.text,
                score=float(score_by_index.get(index, 0.0)),
                rank=rank,
                index=index,
                metadata=dict(document.metadata),
            )
            for rank, (index, document) in enumerate(ranked[:limit], start=1)
        ]
        return RerankResponse(model=self.model_name, results=results)
