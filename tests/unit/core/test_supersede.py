from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from src.core.memory_core import create_memory_core
from src.core.supersede import SupersedeManager
from src.storage import MemoryCoreStore


class TestSupersede(unittest.TestCase):
    def setUp(self) -> None:
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        self.temp_dir = root / f"core-supersede-{uuid.uuid4().hex}"
        self.temp_dir.mkdir()
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.store = MemoryCoreStore(str(self.temp_dir / "test.db"))
        self.store.create_table()
        self.manager = SupersedeManager(self.store)

    def test_detect_conflict_for_replacement_text(self) -> None:
        old = create_memory_core(
            memory_id="mem-old",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-1",
            content_text="周报发给 A",
            tags=["weekly"],
            created_at="2026-04-26T00:00:00Z",
        )
        new = create_memory_core(
            memory_id="mem-new",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-2",
            content_text="周报改为发给 B",
            tags=["weekly"],
            created_at="2026-04-27T00:00:00Z",
        )

        decision = self.manager.detect_conflict(new, [old])

        self.assertTrue(decision.should_supersede)
        self.assertEqual(decision.old_memory_id, "mem-old")

    def test_different_domain_not_supersede(self) -> None:
        old = create_memory_core(
            memory_id="mem-old",
            domain="cli_workflow",
            memory_type="decision",
            scope="project",
            source_type="shell",
            source_ref="event-1",
            content_text="Use command A",
            tags=["cmd"],
        )
        new = create_memory_core(
            memory_id="mem-new",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-2",
            content_text="cmd 改为 command B",
            tags=["cmd"],
        )

        self.assertFalse(self.manager.detect_conflict(new, [old]).should_supersede)

    def test_mark_superseded_and_version_chain(self) -> None:
        old = create_memory_core(
            memory_id="mem-old",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-1",
            content_text="A",
            created_at="2026-04-26T00:00:00Z",
        )
        new = create_memory_core(
            memory_id="mem-new",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-2",
            content_text="B",
            created_at="2026-04-27T00:00:00Z",
        )
        self.store.insert_memory_core(old)
        self.store.insert_memory_core(new)

        self.manager.mark_superseded("mem-old", "mem-new")
        chain = self.manager.get_version_chain("mem-new")

        self.assertEqual(self.store.get_memory("mem-old")["status"], "superseded")
        self.assertEqual([item["memory_id"] for item in chain], ["mem-old", "mem-new"])
