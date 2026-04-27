from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.app.dependencies import get_llm_client, get_memory_core_store
from src.schemas import MemoryHit, RetrieveRequest, RetrieveResponse
from src.storage import MemoryCoreStore


router = APIRouter(prefix="/api/v1", tags=["retrieve"])


def _new_query_id() -> str:
    return f"qry-{uuid.uuid4().hex[:12]}"


def _score_memory(row: dict[str, Any], query_text: str) -> tuple[float, dict[str, float]]:
    content = (row.get("content_text") or "").lower()
    summary = (row.get("summary_text") or "").lower()
    terms = [term for term in query_text.lower().split() if term]
    overlap = 0.0
    if terms:
        matched = sum(1 for term in terms if term in content or term in summary)
        overlap = matched / len(terms)
    importance = float(row.get("importance") or 0.0)
    confidence = float(row.get("confidence") or 0.0)
    score = overlap * 0.5 + importance * 0.25 + confidence * 0.25
    return score, {
        "text_overlap": overlap,
        "importance": importance,
        "confidence": confidence,
    }


def _retrieve_fallback(
    request: RetrieveRequest,
    memory_store: MemoryCoreStore,
) -> RetrieveResponse:
    query_id = _new_query_id()
    rows = memory_store.list_active_memories(limit=max(request.top_k * 5, 20))
    scored: list[tuple[dict[str, Any], float, dict[str, float]]] = []
    for row in rows:
        score, breakdown = _score_memory(row, request.query_text)
        scored.append((row, score, breakdown))
    scored.sort(key=lambda item: item[1], reverse=True)

    hits: list[MemoryHit] = []
    for rank, (row, score, breakdown) in enumerate(scored[: request.top_k], start=1):
        hits.append(
            MemoryHit(
                memory_id=row["memory_id"],
                domain=row["domain"],
                memory_type=row["memory_type"],
                content_text=row["content_text"],
                summary_text=row.get("summary_text"),
                score=score,
                rank=rank,
                scope=row.get("scope"),
                source_ref=row.get("source_ref"),
                tags=list(row.get("tags") or row.get("tags_json") or []),
                entities=list(row.get("entities") or row.get("entities_json") or []),
                score_breakdown=breakdown,
            )
        )

    trace = None
    if request.include_trace:
        trace = {
            "mode": "memory_core_fallback",
            "candidate_count": len(rows),
            "result_count": len(hits),
        }

    return RetrieveResponse(
        status="ok",
        query_id=query_id,
        results=hits,
        trace=trace,
        message="memory_core fallback; domain retrievers not implemented",
    )


@router.post("/retrieve", response_model=RetrieveResponse)
def retrieve_memories(
    request: RetrieveRequest,
    memory_store: MemoryCoreStore = Depends(get_memory_core_store),
    llm_client: object | None = Depends(get_llm_client),
) -> RetrieveResponse:
    del llm_client
    if not request.query_text.strip():
        raise HTTPException(status_code=422, detail="query_text cannot be blank")
    return _retrieve_fallback(request, memory_store)


@router.post("/memories/search", response_model=RetrieveResponse)
def search_memories_alias(
    request: RetrieveRequest,
    memory_store: MemoryCoreStore = Depends(get_memory_core_store),
    llm_client: object | None = Depends(get_llm_client),
) -> RetrieveResponse:
    return retrieve_memories(request, memory_store, llm_client)
