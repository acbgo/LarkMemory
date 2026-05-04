from __future__ import annotations

from src.schemas import EventContext, NormalizedEvent
from src.utils.time import utc_now_iso

from .calendar_models import FeishuCalendarEvent


def calendar_event_to_normalized_event(event: FeishuCalendarEvent) -> NormalizedEvent:
    """将飞书日历事件映射为 NormalizedEvent（1:1）。

    event_type 固定为 "calendar_event"，source_type 固定为 "feishu_calendar"。
    日程标题+描述合并为 content_text，结构化字段存入 payload。
    """
    content_parts = [event.summary]
    if event.description:
        content_parts.append(event.description)
    content_text = "\n".join(content_parts)

    tags = ["calendar", "feishu"]
    if event.status:
        tags.append(event.status)
    if event.recurrence:
        tags.append("recurring")

    occurred_at = event.start_time or utc_now_iso()

    return NormalizedEvent(
        event_id=f"feishu:cal:{event.calendar_event_id}",
        event_type="calendar_event",
        source_type="feishu_calendar",
        occurred_at=occurred_at,
        context=EventContext(
            user_id=event.organizer_id,
            scope="user",
        ),
        title=event.summary,
        content_text=content_text,
        payload={
            "calendar_event_id": event.calendar_event_id,
            "start_time": event.start_time,
            "end_time": event.end_time,
            "attendees": event.attendee_ids,
            "location": event.location,
            "recurrence": event.recurrence,
            "status": event.status,
        },
        raw_payload=dict(event.raw_payload),
        tags=tags,
    )
