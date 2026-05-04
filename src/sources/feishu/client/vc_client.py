from __future__ import annotations

import logging
from typing import Any, Protocol

from src.sources.feishu.events.meeting_models import MeetingChapter, MeetingNotesData, MeetingTodo

logger = logging.getLogger(__name__)


class FeishuVcClientProtocol(Protocol):
    """VC API 调用协议，方便测试时 mock。"""

    def get_recording(self, meeting_id: str) -> str:
        """获取会议录制中的 minute_token。"""
        ...

    def get_notes(self, minute_token: str) -> MeetingNotesData:
        """获取妙记 AI 产物（总结/待办/章节/逐字稿）。"""
        ...


class FeishuVcClient:
    """基于 lark-oapi SDK 的 VC API 客户端。"""

    def __init__(self, api_client: Any) -> None:
        self._client = api_client

    def get_recording(self, meeting_id: str) -> str:
        """调用 vc/v1/meetings/{meeting_id}/recording，返回 minute_token。"""
        from lark_oapi.api.vc.v1 import GetMeetingRecordingRequest  # type: ignore[import-not-found]

        request = GetMeetingRecordingRequest.builder().meeting_id(meeting_id).build()
        response = self._client.vc.v1.meeting_recording.get(request)
        if not response.success():
            raise RuntimeError(
                f"Failed to get recording for meeting {meeting_id}: "
                f"code={response.code} msg={response.msg}"
            )
        recording = getattr(response.data, "recording", None)
        if recording is None:
            raise RuntimeError(f"No recording found for meeting {meeting_id}")
        minute_token = getattr(recording, "minute_token", None)
        if not minute_token:
            raise RuntimeError(f"No minute_token in recording for meeting {meeting_id}")
        return str(minute_token)

    def get_notes(self, minute_token: str) -> MeetingNotesData:
        """调用 vc/v1/minutes/{minute_token}/notes，返回 AI 产物。"""
        from lark_oapi.api.vc.v1 import GetMinuteNotesRequest  # type: ignore[import-not-found]

        request = GetMinuteNotesRequest.builder().minute_token(minute_token).build()
        response = self._client.vc.v1.minutes.notes.get(request)
        if not response.success():
            raise RuntimeError(
                f"Failed to get notes for minute {minute_token}: "
                f"code={response.code} msg={response.msg}"
            )

        data = response.data
        summary = getattr(data, "summary", "") or ""

        todos: list[MeetingTodo] = []
        raw_todos = getattr(data, "todo_list", None) or []
        if isinstance(raw_todos, list):
            for t in raw_todos:
                assignee_ids: list[str] = []
                raw_assignees = getattr(t, "assignees", None) or []
                if isinstance(raw_assignees, list):
                    for a in raw_assignees:
                        a_id = getattr(a, "id", None) or getattr(a, "open_id", None)
                        if a_id:
                            assignee_ids.append(str(a_id))
                todos.append(MeetingTodo(
                    title=getattr(t, "title", "") or "",
                    content=getattr(t, "content", "") or "",
                    due_time=_ts_attr_str(t, "due_time"),
                    assignee_ids=assignee_ids,
                ))

        chapters: list[MeetingChapter] = []
        raw_chapters = getattr(data, "chapter_list", None) or []
        if isinstance(raw_chapters, list):
            for c in raw_chapters:
                chapters.append(MeetingChapter(
                    title=getattr(c, "title", "") or "",
                    start_time_ms=int(getattr(c, "start_time", 0) or 0),
                ))

        verbatim_text = getattr(data, "transcript", "") or ""

        return MeetingNotesData(
            summary=summary,
            todos=todos,
            chapters=chapters,
            verbatim_text=verbatim_text,
            minute_token=minute_token,
        )


def _ts_attr_str(obj: Any, name: str) -> str | None:
    value = getattr(obj, name, None)
    if value is None:
        return None
    if hasattr(value, "timestamp"):
        ts = getattr(value, "timestamp")
        if ts:
            from datetime import datetime, timezone
            try:
                return datetime.fromtimestamp(int(str(ts)), tz=timezone.utc).isoformat()
            except (TypeError, ValueError, OSError):
                pass
    s = str(value)
    return s or None
