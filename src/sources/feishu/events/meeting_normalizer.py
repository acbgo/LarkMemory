from __future__ import annotations

from src.schemas import EventContext, NormalizedEvent
from src.utils.time import utc_now_iso

from .meeting_models import FeishuMeetingEndedEvent, MeetingNotesData, MeetingTodo


def meeting_ended_to_event(meeting: FeishuMeetingEndedEvent) -> NormalizedEvent:
    """会议结束事件→NormalizedEvent（不依赖妙记 AI 产物）。"""
    occurred_at = meeting.end_time or utc_now_iso()

    return NormalizedEvent(
        event_id=f"feishu:meeting:{meeting.meeting_id}",
        event_type="meeting_summary",  # type: ignore[arg-type]
        source_type="feishu_vc",  # type: ignore[arg-type]
        occurred_at=occurred_at,
        context=EventContext(
            user_id=meeting.organizer_id,
            scope="user",
        ),
        title=meeting.topic,
        content_text=meeting.topic,
        payload={
            "meeting_id": meeting.meeting_id,
            "topic": meeting.topic,
            "start_time": meeting.start_time,
            "end_time": meeting.end_time,
            "participants": meeting.participant_ids,
        },
        raw_payload=dict(meeting.raw_payload),
        tags=["meeting", "vc", "feishu"],
    )


def meeting_summary_to_event(
    notes: MeetingNotesData, meeting_id: str, topic: str
) -> NormalizedEvent:
    """妙记 AI 总结→NormalizedEvent。"""
    return NormalizedEvent(
        event_id=f"feishu:meeting:summary:{meeting_id}",
        event_type="meeting_summary",  # type: ignore[arg-type]
        source_type="feishu_vc",  # type: ignore[arg-type]
        occurred_at=utc_now_iso(),
        context=EventContext(scope="user"),
        title=f"{topic} - 会议总结",
        content_text=notes.summary,
        payload={
            "meeting_id": meeting_id,
            "minute_token": notes.minute_token,
            "topic": topic,
            "todo_count": len(notes.todos),
            "chapter_count": len(notes.chapters),
        },
        tags=["meeting", "summary", "feishu"],
    )


def meeting_todo_to_event(
    todo: MeetingTodo, meeting_id: str, minute_token: str, index: int
) -> NormalizedEvent:
    """单条会议待办→NormalizedEvent。"""
    return NormalizedEvent(
        event_id=f"feishu:meeting:todo:{meeting_id}:{index}",
        event_type="meeting_todo",  # type: ignore[arg-type]
        source_type="feishu_vc",  # type: ignore[arg-type]
        occurred_at=utc_now_iso(),
        context=EventContext(scope="user"),
        title=todo.title or f"待办 {index + 1}",
        content_text=f"{todo.title}\n{todo.content}".strip(),
        payload={
            "meeting_id": meeting_id,
            "minute_token": minute_token,
            "todo_title": todo.title,
            "todo_content": todo.content,
            "due_time": todo.due_time,
            "assignees": todo.assignee_ids,
            "todo_index": index,
        },
        tags=["meeting", "todo", "feishu"],
    )


def ingest_notes_to_events(
    notes: MeetingNotesData, meeting_id: str, topic: str
) -> list[NormalizedEvent]:
    """将妙记 AI 产物批量转为 NormalizedEvent 列表（供 processor 和 scanner 共用）。"""
    from src.sources._shared.chunker import split_by_chapters

    events: list[NormalizedEvent] = []

    events.append(meeting_summary_to_event(notes, meeting_id, topic))

    for idx, todo in enumerate(notes.todos):
        events.append(
            meeting_todo_to_event(todo, meeting_id, notes.minute_token, idx)
        )

    chapter_dicts = [
        {"title": ch.title, "start_time_ms": ch.start_time_ms}
        for ch in notes.chapters
    ]
    for chunk in split_by_chapters(notes.verbatim_text, chapter_dicts):
        events.append(
            meeting_chapter_to_event(
                chunk.content,
                chunk.heading or f"章节 {chunk.index + 1}",
                chunk.chunk_id,
                meeting_id,
                notes.minute_token,
                chunk.index,
            )
        )

    return events


def meeting_chapter_to_event(
    chapter_content: str, chapter_title: str, chunk_id: str, meeting_id: str, minute_token: str, index: int
) -> NormalizedEvent:
    """单个会议章节（已切分的逐字稿片段）→NormalizedEvent。event_id 使用内容哈希 chunk_id 保证幂等去重。"""
    return NormalizedEvent(
        event_id=f"feishu:meeting:chapter:{meeting_id}:{chunk_id}",
        event_type="meeting_chapter",  # type: ignore[arg-type]
        source_type="feishu_vc",  # type: ignore[arg-type]
        occurred_at=utc_now_iso(),
        context=EventContext(scope="user"),
        title=chapter_title,
        content_text=chapter_content,
        payload={
            "meeting_id": meeting_id,
            "minute_token": minute_token,
            "chapter_title": chapter_title,
            "chapter_index": index,
        },
        tags=["meeting", "chapter", "feishu"],
    )
