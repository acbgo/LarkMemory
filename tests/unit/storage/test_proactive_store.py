from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from src.storage.proactive_store import ProactiveStore


class TestProactiveStore(unittest.TestCase):
    def setUp(self) -> None:
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        self.temp_dir = root / f"proactive-store-{uuid.uuid4().hex}"
        self.temp_dir.mkdir()
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.store = ProactiveStore(str(self.temp_dir / "proactive.db"))
        self.store.create_table()

    def test_upsert_and_get_record(self) -> None:
        self.store.upsert_record(
            event_id="event-1",
            domain="project_decision",
            push_type="decision_context_push",
            status="sent",
            reason="related_history_found",
            memory_id="mem-1",
            related_memory_ids=["mem-2", "mem-3"],
            target_chat_id="oc_1",
        )

        row = self.store.get_record("event-1", "decision_context_push")

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["status"], "sent")
        self.assertEqual(row["reason"], "related_history_found")
        self.assertEqual(row["memory_id"], "mem-1")
        self.assertEqual(row["target_chat_id"], "oc_1")
        self.assertEqual(row["related_memory_ids"], ["mem-2", "mem-3"])

    def test_upsert_overwrites_existing_status(self) -> None:
        self.store.upsert_record(
            event_id="event-1",
            domain="project_decision",
            push_type="decision_context_push",
            status="failed",
            reason="send_error",
        )
        self.store.upsert_record(
            event_id="event-1",
            domain="project_decision",
            push_type="decision_context_push",
            status="sent",
            reason="retry_ok",
        )

        row = self.store.get_record("event-1", "decision_context_push")

        assert row is not None
        self.assertEqual(row["status"], "sent")
        self.assertEqual(row["reason"], "retry_ok")

    def test_is_sent_only_returns_true_for_sent_status(self) -> None:
        self.store.upsert_record(
            event_id="event-1",
            domain="project_decision",
            push_type="decision_context_push",
            status="failed",
        )
        self.assertFalse(self.store.is_sent("event-1", "decision_context_push"))

        self.store.upsert_record(
            event_id="event-1",
            domain="project_decision",
            push_type="decision_context_push",
            status="sent",
        )
        self.assertTrue(self.store.is_sent("event-1", "decision_context_push"))
