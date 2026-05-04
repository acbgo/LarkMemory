from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

from src.core import MemoryService
from src.domains.team_retention.handler import TeamRetentionDomainHandler
from src.sources.feishu.client.listener import _task_event_from_lark
from src.sources.feishu.events.dispatcher import FeishuEventDispatcher
from src.sources.feishu.events.task_models import FeishuTaskEvent
from src.sources.feishu.events.task_normalizer import task_event_to_normalized_event
from src.storage import EventStore, MemoryCoreStore, TeamRetentionStore


class TestTaskNormalizer(unittest.TestCase):

    def test_normalizer_maps_basic_fields(self) -> None:
        event = FeishuTaskEvent(
            task_id="t_001",
            task_name="完成 Q2 架构设计",
            description="输出架构文档并通过评审",
            status="pending",
            start_time="2026-05-05T09:00:00Z",
            due_time="2026-05-10T18:00:00Z",
            creator_id="ou_creator",
            assignee_ids=["ou_dev_1", "ou_dev_2"],
            follower_ids=["ou_pm"],
            tasklist_name="Q2 项目",
            priority="high",
            url="https://app.feishu.cn/task/t_001",
        )

        normalized = task_event_to_normalized_event(event)

        self.assertEqual(normalized.event_id, "feishu:task:t_001")
        self.assertEqual(normalized.event_type, "task_created")
        self.assertEqual(normalized.source_type, "feishu_task")
        self.assertEqual(normalized.occurred_at, "2026-05-05T09:00:00Z")
        self.assertEqual(normalized.context.user_id, "ou_creator")
        self.assertEqual(normalized.context.scope, "user")
        self.assertEqual(normalized.title, "完成 Q2 架构设计")
        self.assertIn("完成 Q2 架构设计", normalized.content_text)
        self.assertIn("输出架构文档并通过评审", normalized.content_text)
        self.assertIn("task", normalized.tags)
        self.assertIn("feishu", normalized.tags)
        self.assertIn("pending", normalized.tags)
        self.assertIn("high", normalized.tags)

    def test_normalizer_completed_status(self) -> None:
        event = FeishuTaskEvent(
            task_id="t_002",
            task_name="已完成的任务",
            status="completed",
        )

        normalized = task_event_to_normalized_event(event)
        self.assertEqual(normalized.event_type, "task_completed")
        self.assertIn("completed", normalized.tags)

    def test_normalizer_empty_status_defaults_to_task_updated(self) -> None:
        event = FeishuTaskEvent(
            task_id="t_003",
            task_name="状态为空的任务",
            status="",
        )

        normalized = task_event_to_normalized_event(event)
        self.assertEqual(normalized.event_type, "task_updated")

    def test_normalizer_payload_contains_structured_fields(self) -> None:
        event = FeishuTaskEvent(
            task_id="t_004",
            task_name="客户演示准备",
            status="pending",
            due_time="2026-05-12T14:00:00Z",
            assignee_ids=["ou_sales_1"],
            follower_ids=["ou_pm", "ou_designer"],
            tasklist_name="客户项目 A",
            priority="normal",
            url="https://app.feishu.cn/task/t_004",
        )

        normalized = task_event_to_normalized_event(event)
        payload = normalized.payload

        self.assertEqual(payload["task_id"], "t_004")
        self.assertEqual(payload["status"], "pending")
        self.assertEqual(payload["due_time"], "2026-05-12T14:00:00Z")
        self.assertEqual(payload["assignees"], ["ou_sales_1"])
        self.assertEqual(payload["followers"], ["ou_pm", "ou_designer"])
        self.assertEqual(payload["tasklist"], "客户项目 A")
        self.assertEqual(payload["priority"], "normal")
        self.assertEqual(payload["url"], "https://app.feishu.cn/task/t_004")

    def test_normalizer_falls_back_occurred_at_when_no_times(self) -> None:
        event = FeishuTaskEvent(
            task_id="t_005",
            task_name="无时间的任务",
            start_time=None,
            due_time=None,
        )

        normalized = task_event_to_normalized_event(event)
        self.assertTrue(normalized.occurred_at)
        self.assertNotEqual(normalized.occurred_at, "")

    def test_normalizer_uses_due_time_when_no_start_time(self) -> None:
        event = FeishuTaskEvent(
            task_id="t_006",
            task_name="只有截止日的任务",
            start_time=None,
            due_time="2026-05-15T23:59:00Z",
        )

        normalized = task_event_to_normalized_event(event)
        self.assertEqual(normalized.occurred_at, "2026-05-15T23:59:00Z")

    def test_normalizer_empty_description(self) -> None:
        event = FeishuTaskEvent(
            task_id="t_007",
            task_name="无描述任务",
            description="",
        )

        normalized = task_event_to_normalized_event(event)
        self.assertEqual(normalized.content_text, "无描述任务")


class TestTaskEventDispatch(unittest.TestCase):
    def setUp(self) -> None:
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        self.temp_dir = root / f"task-events-{uuid.uuid4().hex}"
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

    def test_dispatch_task_event_stores_event(self) -> None:
        event = FeishuTaskEvent(
            task_id="t_dispatch_1",
            task_name="更新 API 文档",
            status="pending",
            due_time="2026-05-20T18:00:00Z",
            assignee_ids=["ou_dev"],
        )

        normalized = task_event_to_normalized_event(event)
        result = FeishuEventDispatcher(self.service).dispatch_normalized_event(normalized)

        self.assertTrue(result.stored)
        self.assertEqual(result.event_id, "feishu:task:t_dispatch_1")

    def test_dispatch_task_event_ingests_team_retention_memory(self) -> None:
        event = FeishuTaskEvent(
            task_id="t_dispatch_2",
            task_name="请团队长期记住：客户 B 合同 5 月 20 日到期需要续签",
            status="pending",
            due_time="2026-05-20T18:00:00Z",
            creator_id="ou_sales",
        )

        normalized = task_event_to_normalized_event(event)
        result = FeishuEventDispatcher(self.service).dispatch_normalized_event(normalized)

        self.assertTrue(result.stored)
        self.assertGreaterEqual(result.candidate_count, 1)

    def test_dispatch_duplicate_task_event_is_tolerated(self) -> None:
        event = FeishuTaskEvent(
            task_id="t_dup",
            task_name="重复任务事件",
        )

        normalized = task_event_to_normalized_event(event)
        dispatcher = FeishuEventDispatcher(self.service)
        result1 = dispatcher.dispatch_normalized_event(normalized)
        result2 = dispatcher.dispatch_normalized_event(normalized)

        self.assertTrue(result1.stored)
        self.assertTrue(result2.stored)


class TestTaskEventFromLark(unittest.TestCase):

    def test_extracts_basic_fields(self) -> None:
        data = SimpleNamespace(
            event=SimpleNamespace(
                task_id="t_lark_001",
                name="Q2 项目里程碑回顾",
                description="整理 Q2 所有项目里程碑完成情况",
                status="pending",
                start_time=SimpleNamespace(date_time="2026-05-06T09:00:00+08:00"),
                due_time=SimpleNamespace(date_time="2026-05-06T18:00:00+08:00"),
                creator=SimpleNamespace(id="ou_creator"),
                assignees=[
                    SimpleNamespace(id="ou_dev_1"),
                    SimpleNamespace(id="ou_dev_2"),
                ],
                followers=[
                    SimpleNamespace(id="ou_pm"),
                ],
                tasklist=SimpleNamespace(name="Q2 项目跟踪"),
                priority="high",
                url="https://app.feishu.cn/task/t_lark_001",
            ),
        )

        event = _task_event_from_lark(data)
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.task_id, "t_lark_001")
        self.assertEqual(event.task_name, "Q2 项目里程碑回顾")
        self.assertEqual(event.status, "pending")
        self.assertEqual(event.start_time, "2026-05-06T09:00:00+08:00")
        self.assertEqual(event.due_time, "2026-05-06T18:00:00+08:00")
        self.assertEqual(event.creator_id, "ou_creator")
        self.assertEqual(event.assignee_ids, ["ou_dev_1", "ou_dev_2"])
        self.assertEqual(event.follower_ids, ["ou_pm"])
        self.assertEqual(event.tasklist_name, "Q2 项目跟踪")
        self.assertEqual(event.priority, "high")
        self.assertEqual(event.url, "https://app.feishu.cn/task/t_lark_001")

    def test_extracts_name_from_summary_fallback(self) -> None:
        data = SimpleNamespace(
            event=SimpleNamespace(
                task_id="t_lark_002",
                name=None,
                summary="从 summary 取任务名",
                status="pending",
            ),
        )

        event = _task_event_from_lark(data)
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.task_name, "从 summary 取任务名")

    def test_returns_none_when_no_event(self) -> None:
        data = SimpleNamespace(event=None)
        self.assertIsNone(_task_event_from_lark(data))

    def test_returns_none_when_missing_id_or_name(self) -> None:
        data_no_id = SimpleNamespace(
            event=SimpleNamespace(task_id=None, name="test")
        )
        self.assertIsNone(_task_event_from_lark(data_no_id))

        data_no_name = SimpleNamespace(
            event=SimpleNamespace(task_id="t_1", name=None, summary=None)
        )
        self.assertIsNone(_task_event_from_lark(data_no_name))

    def test_empty_assignees_and_followers(self) -> None:
        data = SimpleNamespace(
            event=SimpleNamespace(
                task_id="t_empty_lists",
                name="单人任务",
                status="pending",
                assignees=None,
                followers=None,
            ),
        )
        event = _task_event_from_lark(data)
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.assignee_ids, [])
        self.assertEqual(event.follower_ids, [])

    def test_nested_fields_none_when_outer_is_none(self) -> None:
        data = SimpleNamespace(
            event=SimpleNamespace(
                task_id="t_no_nested",
                name="无嵌套字段",
                status="pending",
                start_time=None,
                due_time=None,
                tasklist=None,
            ),
        )
        event = _task_event_from_lark(data)
        self.assertIsNotNone(event)
        assert event is not None
        self.assertIsNone(event.start_time)
        self.assertIsNone(event.due_time)
        self.assertIsNone(event.tasklist_name)
