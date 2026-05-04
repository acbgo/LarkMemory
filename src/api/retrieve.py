from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from src.app.dependencies import get_memory_service
from src.core import MemoryService
from src.retrieval import RetrievalQuery
from src.schemas import MemoryHit, RetrieveRequest, RetrieveResponse


router = APIRouter(prefix="/api/v1", tags=["retrieve"])
logger = logging.getLogger(__name__)


@router.post("/retrieve", response_model=RetrieveResponse)
async def retrieve_memories(
    request: RetrieveRequest,
    memory_service: MemoryService = Depends(get_memory_service),
) -> RetrieveResponse:
    """接收检索请求，异步调用 MemoryService 并返回排序后的记忆命中结果。"""
    if not request.query_text.strip():
        logger.warning("action=retrieve_memories blank_query")
        raise HTTPException(status_code=422, detail="query_text cannot be blank")
    logger.info(
        "action=retrieve_request_received query_text=%s top_k=%s include_trace=%s user_id=%s project_id=%s",
        request.query_text,
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
    result = await memory_service.retrieve_async(
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
        "action=retrieve_response_ready query_id=%s result_count=%s",
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
async def search_memories_alias(
    request: RetrieveRequest,
    memory_service: MemoryService = Depends(get_memory_service),
) -> RetrieveResponse:
    """兼容 `/memories/search` 别名路由，输入输出与 `retrieve_memories` 相同。"""
    logger.info("action=retrieve_alias_delegate")
    return await retrieve_memories(request, memory_service)
