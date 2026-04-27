from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.app.dependencies import get_llm_client, get_memory_core_store, get_memory_service
from src.core import MemoryService
from src.retrieval import RetrievalQuery
from src.schemas import MemoryHit, RetrieveRequest, RetrieveResponse
from src.storage import MemoryCoreStore


router = APIRouter(prefix="/api/v1", tags=["retrieve"])
logger = logging.getLogger(__name__)


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
    memory_service: MemoryService = Depends(get_memory_service),
) -> RetrieveResponse:
    if not request.query_text.strip():
        logger.warning("function=src.api.retrieve.retrieve_memories action=blank_query")
        raise HTTPException(status_code=422, detail="query_text cannot be blank")
    logger.info(
        "function=src.api.retrieve.retrieve_memories action=build_query top_k=%s include_trace=%s user_id=%s project_id=%s",
        request.top_k,
        request.include_trace,
        request.user_id,
        request.project_id,
    )
    query = RetrievalQuery(
        query_text=request.query_text,
        user_id=request.user_id,
        project_id=request.project_id,
        repo_id=request.repo_id,
        workspace_id=request.workspace_id,
        team_id=request.team_id,
        session_context=request.session_context,
    )
    result = memory_service.retrieve(
        query,
        top_k=request.top_k,
        include_trace=request.include_trace,
    )
    hits = [
        MemoryHit(
            memory_id=ranked.item.memory_id,
            domain=ranked.item.domain.value,
            memory_type=ranked.item.memory_type,
            content_text=ranked.item.content_text,
            summary_text=ranked.item.summary_text,
            score=ranked.final_score,
            rank=ranked.rank,
            scope=ranked.item.scope.value,
            source_ref=ranked.item.source_ref,
            tags=list(ranked.item.tags),
            entities=list(ranked.item.entities),
            score_breakdown=ranked.score_breakdown,
        )
        for ranked in result.ranked_memories
    ]
    logger.info(
        "function=src.api.retrieve.retrieve_memories action=done query_id=%s result_count=%s",
        result.query_id,
        len(hits),
    )
    return RetrieveResponse(
        status="ok",
        query_id=result.query_id,
        results=hits,
        trace=result.trace,
        message=result.message,
    )


@router.post("/memories/search", response_model=RetrieveResponse)
def search_memories_alias(
    request: RetrieveRequest,
    memory_service: MemoryService = Depends(get_memory_service),
) -> RetrieveResponse:
    logger.info("function=src.api.retrieve.search_memories_alias action=delegate")
    return retrieve_memories(request, memory_service)
