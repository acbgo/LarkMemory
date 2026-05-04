from __future__ import annotations

from src.schemas import EventContext, NormalizedEvent
from src.utils.time import utc_now_iso

from .task_models import FeishuTaskEvent


_EVENT_TYPE_MAP: dict[str, str] = {
    "completed": "task_completed",
    "pending": "task_created",
    "": "task_updated",
}


def _infer_event_type(status: str) -> str:
    return _EVENT_TYPE_MAP.get(status, "task_updated")


def task_event_to_normalized_event(event: FeishuTaskEvent) -> NormalizedEvent:
    """将飞书任务事件映射为 NormalizedEvent（1:1）。

    event_type 按 status 区分为 task_created / task_updated / task_completed，
    source_type 固定为 feishu_task。任务名+描述合并为 content_text，
    结构化字段全部存入 payload。
    """
    content_parts = [event.task_name]
    if event.description:
        content_parts.append(event.description)
    content_text = "\n".join(content_parts)

    occurred_at = event.start_time or event.due_time or utc_now_iso()

    tags = ["task", "feishu"]
    if event.status:
        tags.append(event.status)
    if event.priority:
        tags.append(event.priority)

    return NormalizedEvent(
        event_id=f"feishu:task:{event.task_id}",
        event_type=_infer_event_type(event.status),  # type: ignore[arg-type]
        source_type="feishu_task",  # type: ignore[arg-type]
        occurred_at=occurred_at,
        context=EventContext(
            user_id=event.creator_id,
            scope="user",
        ),
        title=event.task_name,
        content_text=content_text,
        payload={
            "task_id": event.task_id,
            "task_name": event.task_name,
            "status": event.status,
            "start_time": event.start_time,
            "due_time": event.due_time,
            "assignees": event.assignee_ids,
            "followers": event.follower_ids,
            "tasklist": event.tasklist_name,
            "priority": event.priority,
            "url": event.url,
        },
        raw_payload=dict(event.raw_payload),
        tags=tags,
    )
