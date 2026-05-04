from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FeishuMeetingEndedEvent:
    """飞书视频会议结束事件，从 WebSocket 回调 payload 提取。"""

    meeting_id: str
    topic: str
    start_time: str | None = None
    end_time: str | None = None
    organizer_id: str | None = None
    participant_ids: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MeetingTodo:
    """会议待办项。"""

    title: str = ""
    content: str = ""
    due_time: str | None = None
    assignee_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MeetingChapter:
    """妙记 AI 章节。"""

    title: str
    start_time_ms: int = 0


@dataclass(slots=True)
class MeetingNotesData:
    """妙记 AI 产物（总结 / 待办 / 章节 / 逐字稿）。"""

    summary: str = ""
    todos: list[MeetingTodo] = field(default_factory=list)
    chapters: list[MeetingChapter] = field(default_factory=list)
    verbatim_text: str = ""
    minute_token: str = ""
