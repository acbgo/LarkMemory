from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

from src.core import MemoryService
from src.domains.project_decision import ProjectDecisionDomainHandler
from src.sources.feishu.client.listener import _calendar_event_from_lark
from src.sources.feishu.events.calendar_models import FeishuCalendarEvent
from src.sources.feishu.events.calendar_normalizer import calendar_event_to_normalized_event
from src.sources.feishu.events.dispatcher import FeishuEventDispatcher
from src.storage import EventStore, MemoryCoreStore


class TestCalendarNormalizer(unittest.TestCase):

    def test_normalizer_maps_basic_fields(self) -> None:
        event = FeishuCalendarEvent(
            calendar_event_id="evt_001",
            summary="项目周会",
            description="讨论 Q2 里程碑进度",
            start_time="2026-05-05T10:00:00+08:00",
            end_time="2026-05-05T11:00:00+08:00",
            organizer_id="ou_organizer",
            attendee_ids=["ou_user_1", "ou_user_2"],
            location="3F-会议室A",
            status="confirmed",
        )

        normalized = calendar_event_to_normalized_event(event)

        self.assertEqual(normalized.event_id, "feishu:cal:evt_001")
        self.assertEqual(normalized.event_type, "calendar_event")
        self.assertEqual(normalized.source_type, "feishu_calendar")
        self.assertEqual(normalized.occurred_at, "2026-05-05T10:00:00+08:00")
        self.assertEqual(normalized.context.user_id, "ou_organizer")
        self.assertEqual(normalized.context.scope, "user")
        self.assertEqual(normalized.title, "项目周会")
        self.assertIn("项目周会", normalized.content_text)
        self.assertIn("Q2 里程碑", normalized.content_text)
        self.assertIn("calendar", normalized.tags)
        self.assertIn("feishu", normalized.tags)
        self.assertIn("confirmed", normalized.tags)

    def test_normalizer_falls_back_occurred_at_when_no_start_time(self) -> None:
        event = FeishuCalendarEvent(
            calendar_event_id="evt_no_start",
            summary="无开始时间的会议",
            start_time=None,
        )

        normalized = calendar_event_to_normalized_event(event)
        self.assertTrue(normalized.occurred_at)
        self.assertNotEqual(normalized.occurred_at, "")

    def test_normalizer_payload_contains_structured_fields(self) -> None:
        event = FeishuCalendarEvent(
            calendar_event_id="evt_002",
            summary="架构评审",
            start_time="2026-05-06T14:00:00Z",
            end_time="2026-05-06T15:30:00Z",
            attendee_ids=["ou_a", "ou_b"],
            location="线上",
            recurrence="FREQ=WEEKLY;BYDAY=FR",
            status="confirmed",
        )

        normalized = calendar_event_to_normalized_event(event)
        payload = normalized.payload

        self.assertEqual(payload["calendar_event_id"], "evt_002")
        self.assertEqual(payload["start_time"], "2026-05-06T14:00:00Z")
        self.assertEqual(payload["end_time"], "2026-05-06T15:30:00Z")
        self.assertEqual(payload["attendees"], ["ou_a", "ou_b"])
        self.assertEqual(payload["location"], "线上")
        self.assertEqual(payload["recurrence"], "FREQ=WEEKLY;BYDAY=FR")
        self.assertIn("recurring", normalized.tags)

    def test_normalizer_empty_description(self) -> None:
        event = FeishuCalendarEvent(
            calendar_event_id="evt_003",
            summary="站会",
            description="",
        )

        normalized = calendar_event_to_normalized_event(event)
        self.assertEqual(normalized.content_text, "站会")

    def test_normalizer_tentative_status(self) -> None:
        event = FeishuCalendarEvent(
            calendar_event_id="evt_004",
            summary="待定会议",
            status="tentative",
        )

        normalized = calendar_event_to_normalized_event(event)
        self.assertIn("tentative", normalized.tags)

    def test_normalizer_cancelled_status(self) -> None:
        event = FeishuCalendarEvent(
            calendar_event_id="evt_005",
            summary="已取消的会议",
            status="cancelled",
        )

        normalized = calendar_event_to_normalized_event(event)
        self.assertIn("cancelled", normalized.tags)


class TestCalendarEventDispatch(unittest.TestCase):
    def setUp(self) -> None:
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        self.temp_dir = root / f"cal-events-{uuid.uuid4().hex}"
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

    def test_dispatch_calendar_event_stores_event(self) -> None:
        event = FeishuCalendarEvent(
            calendar_event_id="evt_dispatch_1",
            summary="技术选型讨论",
            description="讨论是否从 REST 迁移到 GraphQL",
            start_time="2026-05-05T10:00:00Z",
            end_time="2026-05-05T11:00:00Z",
            organizer_id="ou_dev_lead",
            attendee_ids=["ou_dev_1", "ou_dev_2"],
        )

        normalized = calendar_event_to_normalized_event(event)
        result = FeishuEventDispatcher(self.service).dispatch_normalized_event(normalized)

        self.assertTrue(result.stored)
        self.assertEqual(result.event_id, "feishu:cal:evt_dispatch_1")

    def test_dispatch_calendar_event_triggers_project_decision_extraction(self) -> None:
        event = FeishuCalendarEvent(
            calendar_event_id="evt_dispatch_2",
            summary="方案评审",
            description="我们决定采用方案 B 而不是方案 A，因为接入成本更低",
            start_time="2026-05-05T14:00:00Z",
            end_time="2026-05-05T15:00:00Z",
            organizer_id="ou_pm",
        )

        normalized = calendar_event_to_normalized_event(event)
        result = FeishuEventDispatcher(self.service).dispatch_normalized_event(normalized)

        self.assertTrue(result.stored)
        self.assertGreaterEqual(result.candidate_count, 1)

    def test_dispatch_duplicate_calendar_event_is_tolerated(self) -> None:
        event = FeishuCalendarEvent(
            calendar_event_id="evt_dup",
            summary="重复事件",
        )

        normalized = calendar_event_to_normalized_event(event)
        dispatcher = FeishuEventDispatcher(self.service)
        result1 = dispatcher.dispatch_normalized_event(normalized)
        result2 = dispatcher.dispatch_normalized_event(normalized)

        self.assertTrue(result1.stored)
        self.assertTrue(result2.stored)
        self.assertIn("duplicate", str(result2.message or "").lower())


class TestCalendarEventFromLark(unittest.TestCase):

    def test_extracts_basic_fields(self) -> None:
        data = SimpleNamespace(
            event=SimpleNamespace(
                event_id="evt_lark_001",
                summary="项目同步会",
                description="同步本周项目进展",
                start_time=SimpleNamespace(
                    date_time="2026-05-05T10:00:00+08:00",
                ),
                end_time=SimpleNamespace(
                    date_time="2026-05-05T11:00:00+08:00",
                ),
                organizer=SimpleNamespace(id="ou_org"),
                attendees=[
                    SimpleNamespace(id="ou_a"),
                    SimpleNamespace(id="ou_b"),
                ],
                location=SimpleNamespace(name="3F-会议室A"),
                recurrence="FREQ=WEEKLY",
                status="confirmed",
            ),
        )

        event = _calendar_event_from_lark(data)
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.calendar_event_id, "evt_lark_001")
        self.assertEqual(event.summary, "项目同步会")
        self.assertEqual(event.organizer_id, "ou_org")
        self.assertEqual(event.attendee_ids, ["ou_a", "ou_b"])
        self.assertEqual(event.start_time, "2026-05-05T10:00:00+08:00")
        self.assertEqual(event.end_time, "2026-05-05T11:00:00+08:00")
        self.assertEqual(event.location, "3F-会议室A")
        self.assertEqual(event.recurrence, "FREQ=WEEKLY")
        self.assertEqual(event.status, "confirmed")

    def test_returns_none_when_no_event(self) -> None:
        data = SimpleNamespace(event=None)
        self.assertIsNone(_calendar_event_from_lark(data))

    def test_returns_none_when_missing_id_or_summary(self) -> None:
        data_no_id = SimpleNamespace(
            event=SimpleNamespace(event_id=None, summary="test")
        )
        self.assertIsNone(_calendar_event_from_lark(data_no_id))

        data_no_summary = SimpleNamespace(
            event=SimpleNamespace(event_id="evt_1", summary=None)
        )
        self.assertIsNone(_calendar_event_from_lark(data_no_summary))

    def test_empty_attendees_list(self) -> None:
        data = SimpleNamespace(
            event=SimpleNamespace(
                event_id="evt_no_attendees",
                summary="单人会议",
                attendees=None,
            ),
        )
        event = _calendar_event_from_lark(data)
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.attendee_ids, [])

    def test_extracts_organizer_without_id(self) -> None:
        data = SimpleNamespace(
            event=SimpleNamespace(
                event_id="evt_no_org_id",
                summary="无组织者会议",
                organizer=SimpleNamespace(id=None),
            ),
        )
        event = _calendar_event_from_lark(data)
        self.assertIsNotNone(event)
        assert event is not None
        self.assertIsNone(event.organizer_id)

    def test_nested_fields_none_when_outer_is_none(self) -> None:
        data = SimpleNamespace(
            event=SimpleNamespace(
                event_id="evt_no_nested",
                summary="无嵌套字段",
                start_time=None,
                end_time=None,
                location=None,
            ),
        )
        event = _calendar_event_from_lark(data)
        self.assertIsNotNone(event)
        assert event is not None
        self.assertIsNone(event.start_time)
        self.assertIsNone(event.end_time)
        self.assertIsNone(event.location)

    def test_nested_fields_none_when_inner_is_none(self) -> None:
        data = SimpleNamespace(
            event=SimpleNamespace(
                event_id="evt_nested_none_inner",
                summary="嵌套内字段为空",
                start_time=SimpleNamespace(date_time=None),
                location=SimpleNamespace(name=None),
            ),
        )
        event = _calendar_event_from_lark(data)
        self.assertIsNotNone(event)
        assert event is not None
        self.assertIsNone(event.start_time)
        self.assertIsNone(event.location)
