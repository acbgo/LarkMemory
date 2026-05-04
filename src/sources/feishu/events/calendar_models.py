from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FeishuCalendarEvent:
    """飞书日历事件（创建/更新/删除），从 WebSocket 回调 payload 提取。"""

    calendar_event_id: str
    summary: str
    description: str = ""
    start_time: str | None = None
    end_time: str | None = None
    organizer_id: str | None = None
    attendee_ids: list[str] = field(default_factory=list)
    location: str | None = None
    recurrence: str | None = None
    status: str = "confirmed"
    raw_payload: dict[str, Any] = field(default_factory=dict)
