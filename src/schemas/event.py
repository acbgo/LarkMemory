from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


EventType = Literal[
    "calendar_event",
    "command_finished",
    "command_failed",
    "chat_message",
    "doc_changed",
    "meeting_note",
    "memory_feedback",
]

SourceType = Literal[
    "feishu_calendar",
    "openclaw",
    "shell",
    "feishu_chat",
    "feishu_doc",
    "meeting",
    "task_system",
    "user_feedback",
]

ScopeType = Literal[
    "user",
    "project",
    "team",
    "workspace",
    "global",
]


@dataclass(slots=True)
class EventContext:
    user_id: str | None = None
    session_id: str | None = None
    project_id: str | None = None
    team_id: str | None = None
    workspace_id: str | None = None
    repo_id: str | None = None
    thread_id: str | None = None
    scope: ScopeType = "project"


@dataclass(slots=True)
class NormalizedEvent:
    event_id: str
    event_type: EventType
    source_type: SourceType
    occurred_at: str
    context: EventContext
    title: str | None = None
    content_text: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    raw_payload: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
