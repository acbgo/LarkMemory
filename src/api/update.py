from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.app.dependencies import get_memory_service
from src.core import MemoryService
from src.schemas import MemoryUpdateRequest, MemoryUpdateResponse


router = APIRouter(prefix="/api/v1", tags=["update"])


def _require(value: str | float | None, name: str) -> None:
    """校验必填字段，缺失时抛出 400 错误。"""
    if value is None:
        raise HTTPException(status_code=400, detail=f"{name} is required")


def _update_memory_core(
    request: MemoryUpdateRequest,
    memory_service: MemoryService,
) -> MemoryUpdateResponse:
    """根据动作类型执行记忆更新并统一返回结果。"""
    action = request.action

    try:
        if action in {"expire", "forget", "supersede", "confidence", "importance"}:
            result = memory_service.update_memory(
                action,
                memory_id=request.memory_id,
                new_memory_id=request.new_memory_id,
                confidence=request.confidence,
                importance=request.importance,
            )
            return MemoryUpdateResponse(
                status="ok",
                action=result.action,
                memory_id=result.memory_id,
                updated=result.updated,
                message=result.message,
            )
        if action in {"reviewed", "snooze"}:
            result = memory_service.update_memory(
                action,
                memory_id=request.memory_id,
                feedback_signal=request.feedback_signal,
                reviewed_at=request.reviewed_at,
                snooze_days=request.snooze_days,
            )
            return MemoryUpdateResponse(
                status="ok",
                action=result.action,
                memory_id=result.memory_id,
                updated=result.updated,
                message=result.message,
            )
        if action == "feedback":
            if request.memory_id and request.feedback_signal:
                result = memory_service.update_memory(
                    action,
                    memory_id=request.memory_id,
                    feedback_signal=request.feedback_signal,
                )
                return MemoryUpdateResponse(
                    status="accepted",
                    action=result.action,
                    memory_id=result.memory_id,
                    updated=result.updated,
                    message=result.message,
                )
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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="failed to update memory") from exc

    raise HTTPException(status_code=400, detail=f"unsupported action: {action}")


@router.post("/update", response_model=MemoryUpdateResponse)
def update_memory(
    request: MemoryUpdateRequest,
    memory_service: MemoryService = Depends(get_memory_service),
) -> MemoryUpdateResponse:
    """处理记忆更新主路由请求。"""
    return _update_memory_core(request, memory_service)


@router.post("/memories/update", response_model=MemoryUpdateResponse)
def update_memory_alias(
    request: MemoryUpdateRequest,
    memory_service: MemoryService = Depends(get_memory_service),
) -> MemoryUpdateResponse:
    """处理记忆更新别名路由请求。"""
    return _update_memory_core(request, memory_service)
