from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProactiveSuggestion(BaseModel):
    suggestion_id: str
    type: str
    title: str
    content: str
    priority: str = "normal"
    memory_id: str | None = None
    due_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProactiveResponse(BaseModel):
    status: str
    suggestions: list[ProactiveSuggestion]
    message: str | None = None
