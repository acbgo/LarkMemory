from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FeishuTaskEvent:
    """飞书任务事件（创建/更新/完成），从 WebSocket 回调 payload 提取。"""

    task_id: str
    task_name: str
    description: str = ""
    status: str = ""
    start_time: str | None = None
    due_time: str | None = None
    creator_id: str | None = None
    assignee_ids: list[str] = field(default_factory=list)
    follower_ids: list[str] = field(default_factory=list)
    tasklist_name: str | None = None
    priority: str | None = None
    url: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)
