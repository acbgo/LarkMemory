from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FeishuDocChangedEvent:
    """飞书文档变更事件，从 WebSocket 回调 payload 提取。"""

    doc_token: str
    doc_type: str = "docx"
    title: str | None = None
    change_type: str = ""
    user_id: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)
