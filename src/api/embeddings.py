from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.app.dependencies import get_embedding_client
from src.llm import EmbeddingClient
from src.schemas.embeddings import (
    EmbeddingBatchRequest,
    EmbeddingBatchResponsePayload,
    EmbeddingRequest,
    EmbeddingResponsePayload,
)


router = APIRouter(prefix="/api/v1", tags=["embeddings"])


@router.post("/embeddings", response_model=EmbeddingResponsePayload)
def create_embedding(
    request: EmbeddingRequest,
    embedding_client: EmbeddingClient | None = Depends(get_embedding_client),
) -> EmbeddingResponsePayload:
    """Generate one embedding vector through the configured embedding client."""
    if embedding_client is None:
        raise HTTPException(status_code=503, detail="embedding client is not available")
    response = embedding_client.embed_texts([request.text])
    return EmbeddingResponsePayload(
        model=response.model,
        dimension=response.dimensions,
        embedding=response.embeddings[0],
        usage=response.usage,
    )


@router.post("/embeddings/batch", response_model=EmbeddingBatchResponsePayload)
def create_embedding_batch(
    request: EmbeddingBatchRequest,
    embedding_client: EmbeddingClient | None = Depends(get_embedding_client),
) -> EmbeddingBatchResponsePayload:
    """Generate embedding vectors for a non-empty batch of texts."""
    if embedding_client is None:
        raise HTTPException(status_code=503, detail="embedding client is not available")
    response = embedding_client.embed_texts(request.texts)
    return EmbeddingBatchResponsePayload(
        model=response.model,
        dimension=response.dimensions,
        embeddings=response.embeddings,
        usage=response.usage,
    )
