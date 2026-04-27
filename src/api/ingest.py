from __future__ import annotations

import sqlite3
import logging

from fastapi import APIRouter, Depends, HTTPException

from src.app.dependencies import get_memory_service
from src.core import MemoryService
from src.schemas import EventContext, IngestRequest, IngestResponse, NormalizedEvent
from src.utils.ids import event_id as new_event_id
from src.utils.time import utc_now_iso


router = APIRouter(prefix="/api/v1", tags=["ingest"])
logger = logging.getLogger(__name__)


def _model_to_dict(model: object) -> dict[str, object]:
    """将 Pydantic v1/v2 模型转为字典，供 `EventContext` 重建使用。"""
    if hasattr(model, "model_dump"):
        return model.model_dump()  # type: ignore[no-any-return,attr-defined]
    return model.dict()  # type: ignore[no-any-return,attr-defined]


@router.post("/ingest", response_model=IngestResponse)
def ingest_event(
    request: IngestRequest,
    memory_service: MemoryService = Depends(get_memory_service),
) -> IngestResponse:
    """接收标准化事件请求，补齐事件 ID 和时间后返回 MemoryService 的入库结果。"""
    event_id = request.event_id or new_event_id()
    occurred_at = request.occurred_at or utc_now_iso()
    logger.info(
        "function=src.api.ingest.ingest_event action=build_event event_id=%s event_type=%s source_type=%s",
        event_id,
        request.event_type,
        request.source_type,
    )
    event = NormalizedEvent(
        event_id=event_id,
        event_type=request.event_type,  # type: ignore[arg-type]
        source_type=request.source_type,  # type: ignore[arg-type]
        occurred_at=occurred_at,
        context=EventContext(**_model_to_dict(request.context)),
        title=request.title,
        content_text=request.content_text,
        payload=request.payload,
        raw_payload=request.raw_payload,
        tags=request.tags,
    )

    try:
        result = memory_service.ingest_event(event)
    except sqlite3.IntegrityError as exc:
        logger.warning(
            "function=src.api.ingest.ingest_event action=duplicate_event event_id=%s",
            event_id,
        )
        raise HTTPException(
            status_code=409,
            detail=f"event_id already exists: {event_id}",
        ) from exc
    except Exception as exc:
        logger.exception(
            "function=src.api.ingest.ingest_event action=failed event_id=%s",
            event_id,
        )
        raise HTTPException(status_code=500, detail="failed to store event") from exc

    logger.info(
        "function=src.api.ingest.ingest_event action=done event_id=%s stored=%s memory_candidates=%s memory_ids=%s",
        result.event_id,
        result.stored,
        result.candidate_count,
        result.memory_ids,
    )
    return IngestResponse(
        status="ok",
        event_id=result.event_id,
        stored=result.stored,
        memory_ids=result.memory_ids,
        memory_candidates=result.candidate_count,
        message=result.message,
    )
