from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from src.app.dependencies import get_memory_service
from src.core import MemoryService
from src.schemas import EventContext, IngestRequest, IngestResponse, NormalizedEvent


router = APIRouter(prefix="/api/v1", tags=["ingest"])


def _new_event_id() -> str:
    return f"evt-{uuid.uuid4().hex[:12]}"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _model_to_dict(model: object) -> dict[str, object]:
    if hasattr(model, "model_dump"):
        return model.model_dump()  # type: ignore[no-any-return,attr-defined]
    return model.dict()  # type: ignore[no-any-return,attr-defined]


@router.post("/ingest", response_model=IngestResponse)
def ingest_event(
    request: IngestRequest,
    memory_service: MemoryService = Depends(get_memory_service),
) -> IngestResponse:
    event_id = request.event_id or _new_event_id()
    occurred_at = request.occurred_at or _utc_now_iso()
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
        raise HTTPException(
            status_code=409,
            detail=f"event_id already exists: {event_id}",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="failed to store event") from exc

    return IngestResponse(
        status="ok",
        event_id=result.event_id,
        stored=result.stored,
        memory_candidates=result.candidate_count,
        message=result.message,
    )
