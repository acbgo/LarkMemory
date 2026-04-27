from __future__ import annotations

from fastapi import APIRouter, Query

from src.schemas import ProactiveResponse


router = APIRouter(prefix="/api/v1", tags=["proactive"])


@router.get("/proactive", response_model=ProactiveResponse)
def get_proactive_suggestions(
    user_id: str | None = None,
    project_id: str | None = None,
    team_id: str | None = None,
    limit: int = Query(default=10, ge=1, le=50),
) -> ProactiveResponse:
    del user_id, project_id, team_id, limit
    return ProactiveResponse(
        status="ok",
        suggestions=[],
        message="proactive scheduler not implemented",
    )
