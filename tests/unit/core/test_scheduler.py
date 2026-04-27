from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from src.core.decay import DecayPolicy
from src.core.memory_core import create_memory_core
from src.core.scheduler import Scheduler
from src.storage import MemoryCoreStore


class TestScheduler(unittest.TestCase):
    def setUp(self) -> None:
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        self.temp_dir = root / f"core-scheduler-{uuid.uuid4().hex}"
        self.temp_dir.mkdir()
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.store = MemoryCoreStore(str(self.temp_dir / "test.db"))
        self.store.create_table()

    def test_scan_decay_updates_expired(self) -> None:
        self.store.insert_memory_core(
            create_memory_core(
                memory_id="mem-old",
                domain="cli_workflow",
                memory_type="command",
                scope="project",
                source_type="shell",
                source_ref="event-1",
                content_text="npm run build",
                updated_at="2025-01-01T00:00:00Z",
                status="active",
            )
        )
        scheduler = Scheduler(
            self.store,
            DecayPolicy(expire_after_days_by_domain={"cli_workflow": 1.0}),
        )

        result = scheduler.scan_decay()

        self.assertEqual(result.scanned, 1)
        self.assertEqual(result.updated, 1)
        self.assertEqual(self.store.get_memory("mem-old")["status"], "expired")

    def test_scan_decay_continues_after_error(self) -> None:
        self.store.insert_memory_core(
            create_memory_core(
                memory_id="mem-1",
                domain="cli_workflow",
                memory_type="command",
                scope="project",
                source_type="shell",
                source_ref="event-1",
                content_text="npm run build",
                status="active",
            )
        )

        class FailingPolicy:
            def apply(self, memory_store, memory, *, now=None):
                raise RuntimeError("boom")

        result = Scheduler(self.store, FailingPolicy()).scan_decay()  # type: ignore[arg-type]

        self.assertEqual(result.scanned, 1)
        self.assertEqual(len(result.errors), 1)

    def test_review_fallback_and_run_once(self) -> None:
        scheduler = Scheduler(self.store)

        self.assertEqual(scheduler.scan_review_due().suggestions, [])
        self.assertIn("decay", scheduler.run_once())
        self.assertIn("review_due", scheduler.run_once())

