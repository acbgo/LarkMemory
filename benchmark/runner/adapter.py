from __future__ import annotations

import logging
from typing import Any

from src.schemas.event import EventContext, NormalizedEvent

logger = logging.getLogger(__name__)

SOURCE_MAPPING: dict[str, tuple[str, str]] = {
    "cli": ("shell", "command_finished"),
    "feishu_group": ("feishu_chat", "chat_message"),
    "feishu_chat": ("feishu_chat", "chat_message"),
    "feishu_doc": ("feishu_doc", "doc_changed"),
    "feishu_task": ("task_system", "task_updated"),
    "feishu_meeting": ("meeting", "meeting_note"),
}

_DEFAULT_SOURCE = ("feishu_chat", "chat_message")


def convert_event(raw_event: dict[str, Any]) -> NormalizedEvent:
    """Convert a single benchmark event dict to a NormalizedEvent."""
    source_type, event_type = SOURCE_MAPPING.get(
        raw_event.get("source", ""), _DEFAULT_SOURCE,
    )

    ctx = raw_event.get("context") or {}
    context = EventContext(
        user_id=raw_event.get("speaker"),
        project_id=ctx.get("project"),
        team_id=ctx.get("team"),
        workspace_id=ctx.get("workspace"),
    )

    payload = dict(raw_event.get("payload") or {})
    if raw_event.get("source") == "cli":
        if ctx.get("cwd") is not None:
            payload["cwd"] = ctx.get("cwd")
        if raw_event.get("exit_code") is not None:
            payload["exit_code"] = raw_event.get("exit_code")
        if raw_event.get("duration") is not None:
            payload["duration"] = raw_event.get("duration")

    return NormalizedEvent(
        event_id=raw_event["event_id"],
        event_type=event_type,  # type: ignore[arg-type]
        source_type=source_type,  # type: ignore[arg-type]
        occurred_at=raw_event["timestamp"],
        context=context,
        content_text=raw_event.get("content", ""),
        payload=payload,
        raw_payload=raw_event,
    )


def convert_events(raw_events: list[dict[str, Any]]) -> list[NormalizedEvent]:
    """Convert a list of benchmark event dicts, sorted by timestamp."""
    sorted_events = sorted(raw_events, key=lambda e: e.get("timestamp", ""))
    return [convert_event(e) for e in sorted_events]
