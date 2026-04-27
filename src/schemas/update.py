from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


UpdateAction = Literal[
    "feedback",
    "correct",
    "supersede",
    "expire",
    "forget",
    "confidence",
    "importance",
]


class MemoryUpdateRequest(BaseModel):
    action: str
    memory_id: str | None = None
    new_memory_id: str | None = None
    status: str | None = None
    confidence: float | None = None
    importance: float | None = None
    feedback_signal: str | None = None
    content_text: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class MemoryUpdateResponse(BaseModel):
    status: str
    action: str
    memory_id: str | None = None
    updated: bool = False
    message: str | None = None
