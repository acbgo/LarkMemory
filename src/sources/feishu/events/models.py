from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FeishuEventEnvelope:
    """Raw Feishu event envelope kept before domain-agnostic normalization."""

    source_event_id: str
    event_type: str
    received_at: str
    tenant_key: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FeishuMessageEvent:
    """Feishu IM message event extracted from lark-oapi callback payloads."""

    message_id: str
    chat_id: str
    chat_type: str
    sender_id: str | None
    message_type: str
    content_text: str
    create_time: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FeishuCardActionEvent:
    """Feishu interactive-card action normalized for MemoryService update actions."""

    action: str
    memory_id: str | None = None
    operator_id: str | None = None
    chat_id: str | None = None
    snooze_days: int | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)
