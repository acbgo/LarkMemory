from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

from src.core import MemoryService
from src.domains.project_decision import ProjectDecisionDomainHandler
from src.sources._shared.chunker import split_by_chapters
from src.sources.feishu.client.listener import _meeting_ended_from_lark
from src.sources.feishu.events.dispatcher import FeishuEventDispatcher
from src.sources.feishu.events.meeting_models import (
    FeishuMeetingEndedEvent,
    MeetingChapter,
    MeetingNotesData,
    MeetingTodo,
)
from src.sources.feishu.events.meeting_normalizer import (
    meeting_chapter_to_event,
    meeting_ended_to_event,
    meeting_summary_to_event,
    meeting_todo_to_event,
)
from src.sources.feishu.events.meeting_processor import MeetingProcessor
from src.storage import EventStore, MemoryCoreStore
from src.storage.source_state_store import SourceStateStore


class TestMeetingNormalizer(unittest.TestCase):

    def test_meeting_ended_to_event(self) -> None:
        meeting = FeishuMeetingEndedEvent(
            meeting_id="meet_001",
            topic="Q2 架构评审会",
            start_time="2026-05-05T14:00:00Z",
            end_time="2026-05-05T15:00:00Z",
            organizer_id="ou_org",
            participant_ids=["ou_a", "ou_b"],
        )

        event = meeting_ended_to_event(meeting)

        self.assertEqual(event.event_id, "feishu:meeting:meet_001")
        self.assertEqual(event.event_type, "meeting_summary")
        self.assertEqual(event.source_type, "feishu_vc")
        self.assertEqual(event.occurred_at, "2026-05-05T15:00:00Z")
        self.assertEqual(event.title, "Q2 架构评审会")
        self.assertEqual(event.payload["meeting_id"], "meet_001")
        self.assertEqual(event.payload["participants"], ["ou_a", "ou_b"])
        self.assertIn("meeting", event.tags)
        self.assertIn("vc", event.tags)

    def test_meeting_ended_falls_back_occurred_at(self) -> None:
        meeting = FeishuMeetingEndedEvent(
            meeting_id="meet_002",
            topic="无结束时间的会议",
            end_time=None,
        )

        event = meeting_ended_to_event(meeting)
        self.assertTrue(event.occurred_at)

    def test_meeting_summary_to_event(self) -> None:
        notes = MeetingNotesData(
            summary="会议决定采用方案 B，因为接入成本更低。",
            minute_token="min_001",
        )

        event = meeting_summary_to_event(notes, "meet_001", "Q2 架构评审会")

        self.assertEqual(event.event_type, "meeting_summary")
        self.assertEqual(event.source_type, "feishu_vc")
        self.assertIn("采用方案 B", event.content_text)
        self.assertEqual(event.payload["meeting_id"], "meet_001")
        self.assertEqual(event.payload["minute_token"], "min_001")
        self.assertIn("summary", event.tags)

    def test_meeting_todo_to_event(self) -> None:
        todo = MeetingTodo(
            title="完成 API 文档更新",
            content="需要在周五前完成 v2 API 文档",
            due_time="2026-05-08T18:00:00Z",
            assignee_ids=["ou_dev_1"],
        )

        event = meeting_todo_to_event(todo, "meet_001", "min_001", 0)

        self.assertEqual(event.event_type, "meeting_todo")
        self.assertEqual(event.source_type, "feishu_vc")
        self.assertIn("完成 API 文档更新", event.content_text)
        self.assertEqual(event.payload["meeting_id"], "meet_001")
        self.assertEqual(event.payload["due_time"], "2026-05-08T18:00:00Z")
        self.assertEqual(event.payload["assignees"], ["ou_dev_1"])
        self.assertEqual(event.payload["todo_index"], 0)
        self.assertIn("todo", event.tags)

    def test_meeting_todo_empty_title_fallback(self) -> None:
        todo = MeetingTodo(title="", content="内容")

        event = meeting_todo_to_event(todo, "meet_001", "min_001", 2)

        self.assertEqual(event.title, "待办 3")

    def test_meeting_chapter_to_event(self) -> None:
        event = meeting_chapter_to_event(
            "[00:00:01] 大家好\n[00:00:05] 开始讨论",
            "开场介绍",
            "meet_001",
            "min_001",
            0,
        )

        self.assertEqual(event.event_type, "meeting_chapter")
        self.assertEqual(event.source_type, "feishu_vc")
        self.assertEqual(event.title, "开场介绍")
        self.assertIn("开始讨论", event.content_text)
        self.assertEqual(event.payload["chapter_title"], "开场介绍")
        self.assertEqual(event.payload["chapter_index"], 0)
        self.assertIn("chapter", event.tags)


class TestMeetingProcessor(unittest.TestCase):
    def setUp(self) -> None:
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        self.temp_dir = root / f"meeting-proc-{uuid.uuid4().hex}"
        self.temp_dir.mkdir()
        self.addCleanup(shutil.rmtree, self.temp_dir, True)

        self.event_store = EventStore(str(self.temp_dir / "events.db"))
        self.event_store.create_table()
        self.memory_store = MemoryCoreStore(str(self.temp_dir / "memory.db"))
        self.memory_store.create_table()
        self.service = MemoryService(
            event_store=self.event_store,
            memory_store=self.memory_store,
            domain_handlers=[ProjectDecisionDomainHandler(self.memory_store)],
        )
        self.state_store = SourceStateStore(str(self.temp_dir / "source_state.db"))
        self.state_store.create_table()
        self.dispatcher = FeishuEventDispatcher(self.service)

    def _make_notes(self) -> MeetingNotesData:
        return MeetingNotesData(
            summary="会议决定采用方案 B。",
            minute_token="min_test_001",
            todos=[
                MeetingTodo(
                    title="更新文档",
                    content="周五前完成",
                    due_time="2026-05-08T18:00:00Z",
                    assignee_ids=["ou_dev_1"],
                ),
            ],
            chapters=[
                MeetingChapter(title="项目进展", start_time_ms=0),
                MeetingChapter(title="技术讨论", start_time_ms=5000),
            ],
            verbatim_text=(
                "[00:00:01] 进展第一条\n"
                "[00:00:03] 进展第二条\n"
                "[00:00:05] 技术第一条\n"
                "[00:00:08] 技术第二条"
            ),
        )

    class _FakeVcClient:
        def __init__(self, notes: MeetingNotesData) -> None:
            self.notes = notes
            self.recording_calls: list[str] = []
            self.notes_calls: list[str] = []

        def get_recording(self, meeting_id: str) -> str:
            self.recording_calls.append(meeting_id)
            return "min_test_001"

        def get_notes(self, minute_token: str) -> MeetingNotesData:
            self.notes_calls.append(minute_token)
            return self.notes

    def test_processor_full_pipeline(self) -> None:
        notes = self._make_notes()
        vc_client = self._FakeVcClient(notes)
        processor = MeetingProcessor(self.state_store, vc_client, self.dispatcher)

        # 将延迟常量归零以加速测试
        import src.sources.feishu.events.meeting_processor as mp
        orig_delay = mp.AI_GENERATION_DELAY_SECONDS
        orig_retry = mp.RETRY_INTERVAL_SECONDS
        mp.AI_GENERATION_DELAY_SECONDS = 0
        mp.RETRY_INTERVAL_SECONDS = 0
        try:
            processor._process("meet_proc_1", "测试会议")
        finally:
            mp.AI_GENERATION_DELAY_SECONDS = orig_delay
            mp.RETRY_INTERVAL_SECONDS = orig_retry

        self.assertEqual(vc_client.recording_calls, ["meet_proc_1"])
        self.assertEqual(vc_client.notes_calls, ["min_test_001"])

        state = self.state_store.get_state("feishu_vc", "meet_proc_1")
        self.assertIsNotNone(state)
        assert state is not None
        self.assertEqual(state["status"], "complete")

    def test_processor_idempotent_skip(self) -> None:
        self.state_store.upsert_state("feishu_vc", "meet_done", status="complete")
        notes = self._make_notes()
        vc_client = self._FakeVcClient(notes)
        processor = MeetingProcessor(self.state_store, vc_client, self.dispatcher)

        processor._process("meet_done", "已完成会议")

        self.assertEqual(vc_client.recording_calls, [])

    def test_processor_events_dispatched_to_store(self) -> None:
        notes = self._make_notes()
        vc_client = self._FakeVcClient(notes)
        processor = MeetingProcessor(self.state_store, vc_client, self.dispatcher)

        import src.sources.feishu.events.meeting_processor as mp
        orig_delay = mp.AI_GENERATION_DELAY_SECONDS
        orig_retry = mp.RETRY_INTERVAL_SECONDS
        mp.AI_GENERATION_DELAY_SECONDS = 0
        mp.RETRY_INTERVAL_SECONDS = 0
        try:
            processor._process("meet_events", "多事件会议")
        finally:
            mp.AI_GENERATION_DELAY_SECONDS = orig_delay
            mp.RETRY_INTERVAL_SECONDS = orig_retry

        events = self.event_store.list_events(limit=20)
        event_ids = [e["event_id"] for e in events]
        # processor dispatches: 1 summary + 1 todo + 2 chapters
        self.assertTrue(any("summary" in eid for eid in event_ids), f"summary not in {event_ids}")
        self.assertTrue(any("todo" in eid for eid in event_ids), f"todo not in {event_ids}")
        self.assertTrue(any("chapter" in eid for eid in event_ids), f"chapter not in {event_ids}")


class TestMeetingEventFromLark(unittest.TestCase):

    def test_extracts_basic_fields(self) -> None:
        data = SimpleNamespace(
            event=SimpleNamespace(
                meeting_id="meet_lark_001",
                topic="Q2 项目复盘会",
                start_time="2026-05-05T10:00:00Z",
                end_time="2026-05-05T11:30:00Z",
                organizer=SimpleNamespace(id="ou_org"),
                participants=[
                    SimpleNamespace(id="ou_a"),
                    SimpleNamespace(id="ou_b"),
                ],
            ),
        )

        meeting = _meeting_ended_from_lark(data)
        self.assertIsNotNone(meeting)
        assert meeting is not None
        self.assertEqual(meeting.meeting_id, "meet_lark_001")
        self.assertEqual(meeting.topic, "Q2 项目复盘会")
        self.assertEqual(meeting.organizer_id, "ou_org")
        self.assertEqual(meeting.participant_ids, ["ou_a", "ou_b"])

    def test_topic_fallback_to_name(self) -> None:
        data = SimpleNamespace(
            event=SimpleNamespace(
                meeting_id="meet_lark_002",
                topic=None,
                name="未命名",
            ),
        )

        meeting = _meeting_ended_from_lark(data)
        self.assertIsNotNone(meeting)
        assert meeting is not None
        self.assertEqual(meeting.topic, "未命名")

    def test_returns_none_when_no_event(self) -> None:
        data = SimpleNamespace(event=None)
        self.assertIsNone(_meeting_ended_from_lark(data))

    def test_returns_none_when_no_meeting_id(self) -> None:
        data = SimpleNamespace(
            event=SimpleNamespace(meeting_id=None, topic="test")
        )
        self.assertIsNone(_meeting_ended_from_lark(data))


class TestMeetingChapterChunking(unittest.TestCase):

    def test_split_by_chapters_produces_correct_count(self) -> None:
        chapters = [
            {"title": "开场", "start_time_ms": 0},
            {"title": "讨论", "start_time_ms": 5000},
            {"title": "总结", "start_time_ms": 10000},
        ]
        verbatim = (
            "[00:00:01] 开场内容\n"
            "[00:00:03] 更多开场\n"
            "[00:00:05] 讨论内容\n"
            "[00:00:08] 更多讨论\n"
            "[00:00:10] 总结内容"
        )

        chunks = split_by_chapters(verbatim, chapters)
        self.assertEqual(len(chunks), 3)

    def test_normalizer_and_chunker_integration(self) -> None:
        chapters = [{"title": "技术选型", "start_time_ms": 0}]
        verbatim = "[00:00:01] 我们决定用方案 B"

        chunks = split_by_chapters(verbatim, chapters)
        self.assertEqual(len(chunks), 1)

        event = meeting_chapter_to_event(
            chunks[0].content,
            chunks[0].heading or "",
            "meet_int",
            "min_int",
            0,
        )
        self.assertEqual(event.event_type, "meeting_chapter")
        self.assertIn("方案 B", event.content_text)
