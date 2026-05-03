from __future__ import annotations

from pydantic import BaseModel, Field


class EmbeddingRequest(BaseModel):
    text: str = Field(..., min_length=1)


class EmbeddingResponsePayload(BaseModel):
    model: str
    dimension: int
    embedding: list[float]
    usage: dict[str, int] | None = None


class EmbeddingBatchRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, max_length=128)


class EmbeddingBatchResponsePayload(BaseModel):
    model: str
    dimension: int
    embeddings: list[list[float]]
    usage: dict[str, int] | None = None
