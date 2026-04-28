from __future__ import annotations

import json
from typing import Any

from src.schemas import EventContext, NormalizedEvent
from src.utils.time import utc_now_iso

from .models import FeishuMessageEvent


def normalize_message_event(event: FeishuMessageEvent) -> NormalizedEvent:
    """Convert a Feishu IM message into the project's NormalizedEvent contract."""
    occurred_at = _normalize_feishu_time(event.create_time)
    return NormalizedEvent(
        event_id=f"feishu:{event.message_id}",
        event_type="chat_message",
        source_type="feishu_chat",
        occurred_at=occurred_at,
        context=EventContext(
            user_id=event.sender_id,
            team_id=event.chat_id,
            thread_id=event.message_id,
            scope="team",
        ),
        content_text=event.content_text,
        payload={
            "chat_id": event.chat_id,
            "chat_type": event.chat_type,
            "message_id": event.message_id,
            "message_type": event.message_type,
        },
        raw_payload=dict(event.raw_payload),
        tags=["feishu", "im_message"],
    )


def extract_text_from_message_content(message_type: str, content: str | dict[str, Any] | None) -> str:
    """Extract plain text from common Feishu message content formats."""
    if content is None:
        return ""
    data: dict[str, Any]
    if isinstance(content, str):
        try:
            data = json.loads(content or "{}")
        except json.JSONDecodeError:
            return content
    else:
        data = content
    if message_type == "text":
        return str(data.get("text") or "")
    if message_type == "post":
        return _extract_post_text(data)
    return str(data.get("text") or data.get("content") or "")


def _extract_post_text(data: dict[str, Any]) -> str:
    post = data.get("post")
    if not isinstance(post, dict):
        return ""
    zh_cn = post.get("zh_cn") or post.get("en_us") or {}
    content = zh_cn.get("content") if isinstance(zh_cn, dict) else None
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for line in content:
        if not isinstance(line, list):
            continue
        for item in line:
            if isinstance(item, dict) and item.get("tag") == "text":
                parts.append(str(item.get("text") or ""))
    return "".join(parts)


def _normalize_feishu_time(value: str | None) -> str:
    if not value:
        return utc_now_iso()
    if value.isdigit():
        timestamp = int(value)
        if timestamp > 10_000_000_000:
            timestamp = timestamp // 1000
        from datetime import datetime, timezone

        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    return value
