from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.app.dependencies import get_memory_service
from src.core import MemoryService
from src.schemas import ProactiveResponse


router = APIRouter(prefix="/api/v1", tags=["proactive"])


@router.get("/proactive", response_model=ProactiveResponse)
def get_proactive_suggestions(
    user_id: str | None = None,
    project_id: str | None = None,
    team_id: str | None = None,
    workspace_id: str | None = None,
    now: str | None = None,
    warning_window_hours: int = Query(default=24, ge=0, le=168),
    limit: int = Query(default=10, ge=1, le=50),
    memory_service: MemoryService = Depends(get_memory_service),
) -> ProactiveResponse:
    suggestions = memory_service.proactive_suggestions(
        user_id=user_id,
        project_id=project_id,
        team_id=team_id,
        workspace_id=workspace_id,
        limit=limit,
        now=now,
        warning_window_hours=warning_window_hours,
    )
    return ProactiveResponse(
        status="ok",
        suggestions=suggestions,
        message="team_retention review scheduler",
    )
