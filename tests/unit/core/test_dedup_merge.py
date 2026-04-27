from __future__ import annotations

import unittest

from src.core.dedup_merge import DedupMergeEngine
from src.core.memory_core import create_memory_core


class TestDedupMerge(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = DedupMergeEngine()

    def _memory(self, memory_id: str, text: str, *, domain: str = "project_decision", status: str = "active"):
        return create_memory_core(
            memory_id=memory_id,
            domain=domain,
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref=f"event-{memory_id}",
            content_text=text,
            tags=["sqlite"],
            entities=["storage"],
            status=status,
        )

    def test_similarity(self) -> None:
        self.assertEqual(self.engine.similarity("same text", "same text"), 1.0)
        self.assertLess(self.engine.similarity("sqlite storage", "weekly report"), 0.5)

    def test_find_duplicate_same_domain_scope(self) -> None:
        candidate = self._memory("mem-new", "Use SQLite for local storage")
        existing = [self._memory("mem-old", "Use SQLite for local storage")]

        result = self.engine.find_duplicate(candidate, existing)

        self.assertTrue(result.duplicate_found)
        self.assertEqual(result.matched_memory_id, "mem-old")

    def test_different_domain_and_terminal_status_ignored(self) -> None:
        candidate = self._memory("mem-new", "Use SQLite for local storage")
        existing = [
            self._memory("mem-cli", "Use SQLite for local storage", domain="cli_workflow"),
            self._memory("mem-expired", "Use SQLite for local storage", status="expired"),
        ]

        result = self.engine.find_duplicate(candidate, existing)

        self.assertFalse(result.duplicate_found)

    def test_merge_keeps_existing_id_and_merges_lists(self) -> None:
        candidate = self._memory("mem-new", "Use SQLite for local storage with JSON backup")
        existing = self._memory("mem-old", "Use SQLite")

        merged = self.engine.merge(candidate, existing)

        self.assertEqual(merged.memory_id, "mem-old")
        self.assertIn("sqlite", [tag.lower() for tag in merged.tags])
        self.assertIn("storage", [entity.lower() for entity in merged.entities])
        self.assertEqual(merged.content_text, candidate.content_text)

