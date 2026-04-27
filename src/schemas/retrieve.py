from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RetrieveRequest(BaseModel):
    query_text: str = Field(..., min_length=1)
    user_id: str | None = None
    project_id: str | None = None
    repo_id: str | None = None
    workspace_id: str | None = None
    team_id: str | None = None
    session_context: dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=10, ge=1, le=50)
    include_trace: bool = False


class MemoryHit(BaseModel):
    memory_id: str
    domain: str
    memory_type: str
    content_text: str
    summary_text: str | None = None
    score: float
    rank: int
    scope: str | None = None
    source_ref: str | None = None
    tags: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    score_breakdown: dict[str, float] = Field(default_factory=dict)


class RetrieveResponse(BaseModel):
    status: str
    query_id: str
    results: list[MemoryHit]
    trace: dict[str, Any] | None = None
    message: str | None = None
