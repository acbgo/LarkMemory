from __future__ import annotations

import unittest

from src.core.memory_core import MemoryLifecycle, clamp_score, create_memory_core


class TestMemoryCore(unittest.TestCase):
    def test_valid_transition_and_transition_copy(self) -> None:
        lifecycle = MemoryLifecycle()
        memory = create_memory_core(
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-1",
            content_text="Use SQLite",
            status="candidate",
        )

        transitioned = lifecycle.transition(memory, "active", updated_at="2026-04-27T00:00:00Z")

        self.assertTrue(lifecycle.can_transition("candidate", "active"))
        self.assertEqual(memory.status, "candidate")
        self.assertEqual(transitioned.status, "active")
        self.assertEqual(transitioned.updated_at, "2026-04-27T00:00:00Z")

    def test_invalid_transition_raises(self) -> None:
        lifecycle = MemoryLifecycle()

        with self.assertRaisesRegex(ValueError, "forgotten -> active"):
            lifecycle.validate_transition("forgotten", "active")

    def test_create_memory_core_autofills_id_time_and_cleans_content(self) -> None:
        memory = create_memory_core(
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-1",
            content_text="  Use\nSQLite  ",
        )

        self.assertTrue(memory.memory_id.startswith("mem-"))
        self.assertEqual(memory.content_text, "Use SQLite")
        self.assertIsNotNone(memory.created_at)
        self.assertIsNotNone(memory.updated_at)

    def test_create_memory_core_rejects_empty_content_and_bad_scores(self) -> None:
        kwargs = {
            "domain": "project_decision",
            "memory_type": "decision",
            "scope": "project",
            "source_type": "feishu_chat",
            "source_ref": "event-1",
        }
        with self.assertRaises(ValueError):
            create_memory_core(content_text="   ", **kwargs)
        with self.assertRaises(ValueError):
            create_memory_core(content_text="ok", importance=1.1, **kwargs)
        with self.assertRaises(ValueError):
            create_memory_core(content_text="ok", confidence=-0.1, **kwargs)
        with self.assertRaises(ValueError):
            clamp_score(2.0)

