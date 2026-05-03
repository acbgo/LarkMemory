from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RerankDocumentPayload(BaseModel):
    id: str
    text: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RerankRequest(BaseModel):
    query: str = Field(..., min_length=1)
    documents: list[RerankDocumentPayload] = Field(..., min_length=1, max_length=128)
    top_k: int | None = Field(default=None, ge=1, le=128)


class RerankResultPayload(BaseModel):
    id: str
    text: str
    score: float
    rank: int
    index: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class RerankResponsePayload(BaseModel):
    model: str
    results: list[RerankResultPayload]
