from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EventContextPayload(BaseModel):
    user_id: str | None = None
    session_id: str | None = None
    project_id: str | None = None
    team_id: str | None = None
    workspace_id: str | None = None
    repo_id: str | None = None
    thread_id: str | None = None
    scope: str = "project"


class IngestRequest(BaseModel):
    event_id: str | None = None
    event_type: str
    source_type: str
    occurred_at: str | None = None
    context: EventContextPayload = Field(default_factory=EventContextPayload)
    title: str | None = None
    content_text: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class IngestResponse(BaseModel):
    status: str
    event_id: str
    stored: bool
    memory_candidates: int = 0
    message: str | None = None
