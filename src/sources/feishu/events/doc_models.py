from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FeishuDocChangedEvent:
    """飞书文档编辑事件（drive.file.edit_v1），从 WebSocket 回调 payload 提取。"""

    file_token: str
    file_type: str = "docx"
    user_id: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)
