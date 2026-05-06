from __future__ import annotations

import asyncio
import shutil
import unittest
import uuid
from pathlib import Path

from src.core import MemoryService
from src.domains.team_retention.handler import TeamRetentionDomainHandler
from src.sources.feishu.events import FeishuEventDispatcher, FeishuMessageEvent, normalize_message_event
from src.schemas import EventContext, NormalizedEvent
from src.storage import EventStore, MemoryCoreStore, TeamRetentionStore


class TestFeishuEvents(unittest.TestCase):
    def setUp(self) -> None:
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        self.temp_dir = root / f"feishu-events-{uuid.uuid4().hex}"
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

    def test_normalize_message_event_maps_feishu_fields(self) -> None:
        event = FeishuMessageEvent(
            message_id="om_msg_1",
            chat_id="oc_chat_1",
            chat_type="group",
            sender_id="ou_user_1",
            message_type="text",
            content_text="请团队长期记住：客户 A 要求导出 xlsx。",
            create_time="1777132800000",
            raw_payload={"event": "raw"},
        )

        normalized = normalize_message_event(event)

        self.assertEqual(normalized.event_id, "feishu:om_msg_1")
        self.assertEqual(normalized.source_type, "feishu_chat")
        self.assertEqual(normalized.context.team_id, "oc_chat_1")
        self.assertEqual(normalized.context.user_id, "ou_user_1")
        self.assertEqual(normalized.context.scope, "team")
        self.assertIn("feishu", normalized.tags)

    def test_dispatch_message_ingests_team_retention_memory(self) -> None:
        event = FeishuMessageEvent(
            message_id="om_msg_2",
            chat_id="oc_chat_1",
            chat_type="group",
            sender_id="ou_user_1",
            message_type="text",
            content_text="请团队长期记住：API key 已更新到 secret-v2，旧 key 不再使用。",
            create_time="2026-04-27T00:00:00Z",
        )

        result = FeishuEventDispatcher(self.service).dispatch_message(event)

        self.assertTrue(result.stored)
        self.assertEqual(result.candidate_count, 1)
        memory_id = result.memory_ids[0]
        self.assertEqual(self.memory_store.get_memory(memory_id)["domain"], "team_retention")
        self.assertIsNotNone(self.team_store.get_review_schedule(memory_id))

    def test_dispatch_duplicate_message_is_tolerated(self) -> None:
        event = FeishuMessageEvent(
            message_id="om_msg_dup",
            chat_id="oc_chat_1",
            chat_type="group",
            sender_id="ou_user_1",
            message_type="text",
            content_text="请团队长期记住：客户 A 要求导出 xlsx。",
        )
        dispatcher = FeishuEventDispatcher(self.service)

        first = dispatcher.dispatch_message(event)
        second = dispatcher.dispatch_message(event)

        self.assertEqual(len(first.memory_ids), 1)
        self.assertEqual(second.message, "duplicate feishu event ignored")

    def test_dispatch_normalized_event_runs_ingest_outside_active_event_loop(self) -> None:
        class LoopSensitiveService:
            def ingest_event(self, event):
                try:
                    asyncio.get_running_loop()
                except RuntimeError:
                    return type(
                        "Result",
                        (),
                        {
                            "event_id": event.event_id,
                            "stored": True,
                            "memory_ids": [],
                            "candidate_count": 0,
                            "message": "ok",
                        },
                    )()
                raise AssertionError("ingest_event should not run inside an active event loop")

        event = NormalizedEvent(
            event_id="feishu:event-loop",
            event_type="chat_message",
            source_type="feishu_chat",
            occurred_at="2026-04-27T00:00:00Z",
            context=EventContext(team_id="oc_chat_1"),
            content_text="请团队长期记住：测试事件循环隔离。",
        )

        async def dispatch_inside_loop():
            return FeishuEventDispatcher(LoopSensitiveService()).dispatch_normalized_event(event)  # type: ignore[arg-type]

        result = asyncio.run(dispatch_inside_loop())

        self.assertTrue(result.stored)
        self.assertEqual(result.message, "ok")
