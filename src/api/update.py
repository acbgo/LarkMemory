from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.app.dependencies import get_memory_core_store
from src.schemas import MemoryUpdateRequest, MemoryUpdateResponse
from src.storage import MemoryCoreStore


router = APIRouter(prefix="/api/v1", tags=["update"])


def _require(value: str | float | None, name: str) -> None:
    if value is None:
        raise HTTPException(status_code=400, detail=f"{name} is required")


def _update_memory_core(
    request: MemoryUpdateRequest,
    memory_store: MemoryCoreStore,
) -> MemoryUpdateResponse:
    action = request.action

    try:
        if action == "expire":
            _require(request.memory_id, "memory_id")
            memory_store.update_memory_status(request.memory_id or "", "expired")
            return MemoryUpdateResponse(
                status="ok",
                action=action,
                memory_id=request.memory_id,
                updated=True,
            )
        if action == "forget":
            _require(request.memory_id, "memory_id")
            memory_store.update_memory_status(request.memory_id or "", "forgotten")
            return MemoryUpdateResponse(
                status="ok",
                action=action,
                memory_id=request.memory_id,
                updated=True,
            )
        if action == "supersede":
            _require(request.memory_id, "memory_id")
            _require(request.new_memory_id, "new_memory_id")
            memory_store.mark_superseded(
                request.memory_id or "",
                request.new_memory_id or "",
            )
            return MemoryUpdateResponse(
                status="ok",
                action=action,
                memory_id=request.memory_id,
                updated=True,
            )
        if action == "confidence":
            _require(request.memory_id, "memory_id")
            _require(request.confidence, "confidence")
            memory_store.update_confidence(request.memory_id or "", request.confidence or 0.0)
            return MemoryUpdateResponse(
                status="ok",
                action=action,
                memory_id=request.memory_id,
                updated=True,
            )
        if action == "importance":
            _require(request.memory_id, "memory_id")
            _require(request.importance, "importance")
            memory_store.update_importance(request.memory_id or "", request.importance or 0.0)
            return MemoryUpdateResponse(
                status="ok",
                action=action,
                memory_id=request.memory_id,
                updated=True,
            )
        if action == "feedback":
            return MemoryUpdateResponse(
                status="accepted",
                action=action,
                memory_id=request.memory_id,
                updated=False,
                message="feedback accepted; access log store not implemented",
            )
        if action == "correct":
            return MemoryUpdateResponse(
                status="accepted",
                action=action,
                memory_id=request.memory_id,
                updated=False,
                message="correction accepted; core lifecycle service not implemented",
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="failed to update memory") from exc

    raise HTTPException(status_code=400, detail=f"unsupported action: {action}")


@router.post("/update", response_model=MemoryUpdateResponse)
def update_memory(
    request: MemoryUpdateRequest,
    memory_store: MemoryCoreStore = Depends(get_memory_core_store),
) -> MemoryUpdateResponse:
    return _update_memory_core(request, memory_store)


@router.post("/memories/update", response_model=MemoryUpdateResponse)
def update_memory_alias(
    request: MemoryUpdateRequest,
    memory_store: MemoryCoreStore = Depends(get_memory_core_store),
) -> MemoryUpdateResponse:
    return _update_memory_core(request, memory_store)
