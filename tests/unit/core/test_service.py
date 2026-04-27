from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from src.core.memory_core import create_memory_core
from src.core.service import MemoryService
from src.retrieval import RetrievalQuery
from src.schemas import EventContext, NormalizedEvent
from src.storage import EventStore, MemoryCoreStore


class TestService(unittest.TestCase):
    def setUp(self) -> None:
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        self.temp_dir = root / f"core-service-{uuid.uuid4().hex}"
        self.temp_dir.mkdir()
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.event_store = EventStore(str(self.temp_dir / "events.db"))
        self.event_store.create_table()
        self.memory_store = MemoryCoreStore(str(self.temp_dir / "memory.db"))
        self.memory_store.create_table()
        self.service = MemoryService(
            event_store=self.event_store,
            memory_store=self.memory_store,
        )

    def test_ingest_event_writes_event_store(self) -> None:
        event = NormalizedEvent(
            event_id="event-1",
            event_type="chat_message",
            source_type="feishu_chat",
            occurred_at="2026-04-27T00:00:00Z",
            context=EventContext(),
            content_text="决定采用方案 B",
        )

        result = self.service.ingest_event(event)

        self.assertTrue(result.stored)
        self.assertIsNotNone(self.event_store.get_event("event-1"))

    def test_add_memory_and_duplicate(self) -> None:
        memory = create_memory_core(
            memory_id="mem-1",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-1",
            content_text="Use SQLite",
            importance=0.9,
            confidence=0.9,
            status="active",
        )
        duplicate = create_memory_core(
            memory_id="mem-2",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-2",
            content_text="Use SQLite",
            importance=0.9,
            confidence=0.9,
            status="active",
        )

        self.assertEqual(self.service.add_memory(memory), "mem-1")
        self.assertEqual(self.service.add_memory(duplicate), "mem-1")

    def test_retrieve_empty_and_with_memory(self) -> None:
        empty = self.service.retrieve(RetrievalQuery("sqlite"), include_trace=True)
        self.assertEqual(empty.ranked_memories, [])
        self.assertEqual(empty.trace["mode"], "memory_core_fallback")

        self.memory_store.insert_memory_core(
            create_memory_core(
                memory_id="mem-1",
                domain="project_decision",
                memory_type="decision",
                scope="project",
                source_type="feishu_chat",
                source_ref="event-1",
                content_text="Use SQLite",
                importance=0.9,
                confidence=0.9,
                status="active",
            )
        )
        result = self.service.retrieve(RetrievalQuery("sqlite"), top_k=1)

        self.assertEqual(len(result.ranked_memories), 1)
        self.assertEqual(result.ranked_memories[0].item.memory_id, "mem-1")

    def test_update_actions(self) -> None:
        for memory_id, text in [("mem-old", "old"), ("mem-new", "new"), ("mem-score", "score")]:
            self.memory_store.insert_memory_core(
                create_memory_core(
                    memory_id=memory_id,
                    domain="project_decision",
                    memory_type="decision",
                    scope="project",
                    source_type="feishu_chat",
                    source_ref=f"event-{memory_id}",
                    content_text=text,
                    status="active",
                )
            )

        self.assertTrue(self.service.update_memory("expire", memory_id="mem-score").updated)
        self.assertEqual(self.memory_store.get_memory("mem-score")["status"], "expired")
        self.assertTrue(self.service.update_memory("supersede", memory_id="mem-old", new_memory_id="mem-new").updated)
        self.assertEqual(self.memory_store.get_memory("mem-old")["status"], "superseded")
        self.assertTrue(self.service.update_memory("confidence", memory_id="mem-new", confidence=0.7).updated)
        self.assertTrue(self.service.update_memory("importance", memory_id="mem-new", importance=0.8).updated)
        feedback = self.service.update_memory("feedback", memory_id="mem-new", feedback_signal="useful")
        self.assertFalse(feedback.updated)

    def test_proactive_and_maintenance(self) -> None:
        self.assertEqual(self.service.proactive_suggestions(), [])
        self.assertIn("decay", self.service.run_maintenance())

