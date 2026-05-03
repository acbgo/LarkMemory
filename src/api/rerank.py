from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from src.app.dependencies import get_rerank_client
from src.llm import RerankClient
from src.llm.rerank_base import RerankDocument
from src.schemas.rerank import RerankRequest, RerankResponsePayload, RerankResultPayload


router = APIRouter(prefix="/api/v1", tags=["rerank"])
logger = logging.getLogger(__name__)


@router.post("/rerank", response_model=RerankResponsePayload)
def rerank_documents(
    request: RerankRequest,
    rerank_client: RerankClient | None = Depends(get_rerank_client),
) -> RerankResponsePayload:
    """Rank documents with the configured rerank service."""
    if rerank_client is None:
        raise HTTPException(status_code=503, detail="rerank client is not available")
    try:
        response = rerank_client.rerank(
            request.query,
            [
                RerankDocument(id=item.id, text=item.text, metadata=dict(item.metadata))
                for item in request.documents
            ],
            top_k=request.top_k,
        )
    except Exception as exc:
        logger.warning("action=rerank_upstream_failed document_count=%s", len(request.documents), exc_info=True)
        raise HTTPException(status_code=502, detail="rerank upstream failed") from exc
    return RerankResponsePayload(
        model=response.model,
        results=[
            RerankResultPayload(
                id=item.id,
                text=item.text,
                score=item.score,
                rank=item.rank,
                index=item.index,
                metadata=dict(item.metadata),
            )
            for item in response.results
        ],
    )
