from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from src.core.decay import DecayPolicy
from src.core.memory_core import create_memory_core
from src.storage import MemoryCoreStore


class TestDecay(unittest.TestCase):
    def test_freshness_decays_and_default_for_missing_time(self) -> None:
        policy = DecayPolicy()

        fresh = policy.freshness("2026-04-27T00:00:00Z", domain="cli_workflow", now="2026-04-27T00:00:00Z")
        old = policy.freshness("2026-03-28T00:00:00Z", domain="cli_workflow", now="2026-04-27T00:00:00Z")

        self.assertGreater(fresh, old)
        self.assertEqual(policy.freshness(None, domain="cli_workflow"), 0.3)

    def test_expire_rules_by_domain(self) -> None:
        policy = DecayPolicy()
        cli = create_memory_core(
            domain="cli_workflow",
            memory_type="command",
            scope="project",
            source_type="shell",
            source_ref="event-1",
            content_text="npm run build",
            updated_at="2025-01-01T00:00:00Z",
            status="active",
        )
        team = create_memory_core(
            domain="team_retention",
            memory_type="fact",
            scope="team",
            source_type="feishu_chat",
            source_ref="event-2",
            content_text="critical fact",
            updated_at="2025-01-01T00:00:00Z",
            status="active",
        )

        self.assertEqual(policy.evaluate(cli, now="2026-04-27T00:00:00Z").new_status, "expired")
        self.assertIsNone(policy.evaluate(team, now="2026-04-27T00:00:00Z").new_status)

    def test_apply_updates_status(self) -> None:
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        temp_dir = root / f"core-decay-{uuid.uuid4().hex}"
        temp_dir.mkdir()
        self.addCleanup(shutil.rmtree, temp_dir, True)
        store = MemoryCoreStore(str(temp_dir / "test.db"))
        store.create_table()
        memory = create_memory_core(
            memory_id="mem-cli",
            domain="cli_workflow",
            memory_type="command",
            scope="project",
            source_type="shell",
            source_ref="event-1",
            content_text="npm run build",
            updated_at="2025-01-01T00:00:00Z",
            status="active",
        )
        store.insert_memory_core(memory)

        DecayPolicy().apply(store, store.get_memory("mem-cli"), now="2026-04-27T00:00:00Z")

        self.assertEqual(store.get_memory("mem-cli")["status"], "expired")

