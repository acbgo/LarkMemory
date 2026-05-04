from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from src.core import MemoryService
from src.domains.team_retention.handler import TeamRetentionDomainHandler
from src.sources.feishu.events.dispatcher import FeishuEventDispatcher
from src.sources.feishu.events.meeting_models import (
    MeetingChapter,
    MeetingNotesData,
    MeetingTodo,
)
from src.sources.feishu.scanner.meeting_scanner import MeetingScanner
from src.storage import EventStore, MemoryCoreStore, TeamRetentionStore
from src.storage.source_state_store import SourceStateStore


class TestMeetingScanner(unittest.TestCase):
    def setUp(self) -> None:
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        self.temp_dir = root / f"meeting-scanner-{uuid.uuid4().hex}"
        self.temp_dir.mkdir()
        self.addCleanup(shutil.rmtree, self.temp_dir, True)

        self.event_store = EventStore(str(self.temp_dir / "events.db"))
        self.event_store.create_table()
        self.memory_store = MemoryCoreStore(str(self.temp_dir / "memory.db"))
        self.memory_store.create_table()
        self.team_store = TeamRetentionStore(str(self.temp_dir / "memory.db"))
        self.team_store.create_table()
        self.service = MemoryService(
            event_store=self.event_store,
            memory_store=self.memory_store,
            domain_handlers=[TeamRetentionDomainHandler(self.memory_store, self.team_store)],
        )
        self.state_store = SourceStateStore(str(self.temp_dir / "source_state.db"))
        self.state_store.create_table()
        self.dispatcher = FeishuEventDispatcher(self.service)

    def _make_notes(self) -> MeetingNotesData:
        return MeetingNotesData(
            summary="补处理的会议总结。",
            minute_token="min_scanner_001",
            todos=[MeetingTodo(title="补处理待办", content="内容")],
            chapters=[MeetingChapter(title="补处理章节", start_time_ms=0)],
            verbatim_text="[00:00:01] 补处理内容",
        )

    class _FakeVcClient:
        def __init__(self, notes: MeetingNotesData) -> None:
            self.notes = notes
            self.notes_calls: list[str] = []

        def get_recording(self, meeting_id: str) -> str:
            return "min_scanner_001"

        def get_notes(self, minute_token: str) -> MeetingNotesData:
            self.notes_calls.append(minute_token)
            return self.notes

    def test_scanner_processes_pending_meeting(self) -> None:
        notes = self._make_notes()
        vc_client = self._FakeVcClient(notes)
        scanner = MeetingScanner(self.state_store, vc_client, self.dispatcher)

        # 写入一条 pending 记录
        self.state_store.upsert_state(
            "feishu_vc",
            "meet_scan_1",
            status="pending_ai",
            metadata={"minute_token": "min_scanner_001", "topic": "待补处理会议"},
        )

        processed = scanner.run()
        self.assertEqual(processed, 1)

        state = self.state_store.get_state("feishu_vc", "meet_scan_1")
        self.assertEqual(state["status"], "complete")

    def test_scanner_skips_already_complete(self) -> None:
        notes = self._make_notes()
        vc_client = self._FakeVcClient(notes)
        scanner = MeetingScanner(self.state_store, vc_client, self.dispatcher)

        self.state_store.upsert_state("feishu_vc", "meet_done", status="complete")

        processed = scanner.run()
        self.assertEqual(processed, 0)
        self.assertEqual(vc_client.notes_calls, [])

    def test_scanner_skips_dead_letter(self) -> None:
        notes = self._make_notes()
        vc_client = self._FakeVcClient(notes)
        scanner = MeetingScanner(self.state_store, vc_client, self.dispatcher)

        self.state_store.upsert_state(
            "feishu_vc",
            "meet_dead",
            status="pending_ai",
            metadata={"minute_token": "min_scanner_001", "topic": "死信"},
        )
        # 手动设置 error_count 超过上限
        for _ in range(12):
            self.state_store.mark_error("feishu_vc", "meet_dead")

        processed = scanner.run()
        self.assertEqual(processed, 0)
        self.assertEqual(vc_client.notes_calls, [])

    def test_scanner_marks_error_when_notes_still_empty(self) -> None:
        empty_notes = MeetingNotesData(minute_token="min_empty")
        vc_client = self._FakeVcClient(empty_notes)
        scanner = MeetingScanner(self.state_store, vc_client, self.dispatcher)

        self.state_store.upsert_state(
            "feishu_vc",
            "meet_empty",
            status="pending_ai",
            metadata={"minute_token": "min_empty", "topic": "空产物"},
        )

        processed = scanner.run()
        self.assertEqual(processed, 0)

        state = self.state_store.get_state("feishu_vc", "meet_empty")
        self.assertEqual(state["status"], "error")

    def test_scanner_no_minute_token_marks_error(self) -> None:
        notes = self._make_notes()
        vc_client = self._FakeVcClient(notes)
        scanner = MeetingScanner(self.state_store, vc_client, self.dispatcher)

        self.state_store.upsert_state(
            "feishu_vc",
            "meet_no_token",
            status="pending_ai",
            metadata={"topic": "无minute_token"},
        )

        processed = scanner.run()
        self.assertEqual(processed, 0)

        state = self.state_store.get_state("feishu_vc", "meet_no_token")
        self.assertEqual(state["status"], "error")

    def test_scanner_dispatches_events(self) -> None:
        notes = self._make_notes()
        vc_client = self._FakeVcClient(notes)
        scanner = MeetingScanner(self.state_store, vc_client, self.dispatcher)

        self.state_store.upsert_state(
            "feishu_vc",
            "meet_events",
            status="pending_ai",
            metadata={"minute_token": "min_scanner_001", "topic": "事件测试"},
        )

        processed = scanner.run()
        self.assertEqual(processed, 1)

        events = self.event_store.list_events(limit=20)
        event_ids = [e["event_id"] for e in events]
        self.assertTrue(any("summary" in eid for eid in event_ids))
        self.assertTrue(any("todo" in eid for eid in event_ids))
        self.assertTrue(any("chapter" in eid for eid in event_ids))
