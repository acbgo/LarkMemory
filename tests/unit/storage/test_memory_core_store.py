from __future__ import annotations

import unittest
import uuid
import shutil
from pathlib import Path

from src.schemas import MemoryCore
from src.storage import MemoryCoreStore


class TestMemoryCoreStore(unittest.TestCase):
    def setUp(self) -> None:
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        self.temp_dir = root / f"memory-core-store-{uuid.uuid4().hex}"
        self.temp_dir.mkdir()
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.db_path = str(self.temp_dir / "test.db")
        self.store = MemoryCoreStore(self.db_path)
        self.store.create_table()

    def test_insert_and_get_memory(self) -> None:
        memory = MemoryCore(
            memory_id="memory-1",
            domain="cli_workflow",
            memory_type="command_template",
            scope="project",
            source_type="shell",
            source_ref="event-1",
            source_event_id="event-1",
            content_text="npm run build",
            summary_text="Build command",
            entities=["npm", "build"],
            tags=["build"],
            importance=0.7,
            confidence=0.9,
            created_at="2026-04-26T12:00:00Z",
            updated_at="2026-04-26T12:00:00Z",
        )

        inserted_id = self.store.insert_memory_core(memory)
        fetched = self.store.get_memory(inserted_id)

        self.assertEqual(inserted_id, "memory-1")
        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched["domain"], "cli_workflow")
        self.assertEqual(fetched["entities_json"], ["npm", "build"])
        self.assertEqual(fetched["tags_json"], ["build"])
        self.assertEqual(fetched["confidence"], 0.9)

    def test_mark_superseded_updates_status_and_link(self) -> None:
        old_memory = MemoryCore(
            memory_id="memory-old",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-1",
            content_text="Use SQLite",
        )
        new_memory = MemoryCore(
            memory_id="memory-new",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-2",
            content_text="Use PostgreSQL",
        )

        self.store.insert_memory_core(old_memory)
        self.store.insert_memory_core(new_memory)
        self.store.mark_superseded("memory-old", "memory-new")

        fetched = self.store.get_memory("memory-old")
        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched["status"], "superseded")
        self.assertEqual(fetched["superseded_by"], "memory-new")
        new_fetched = self.store.get_memory("memory-new")
        self.assertIsNotNone(new_fetched)
        assert new_fetched is not None
        self.assertEqual(new_fetched["overwrite_of"], "memory-old")

    def test_list_active_memories_filters_out_non_active(self) -> None:
        active = MemoryCore(
            memory_id="memory-active",
            domain="cli_workflow",
            memory_type="command_template",
            scope="project",
            source_type="shell",
            source_ref="event-1",
            content_text="npm run build",
        )
        candidate = MemoryCore(
            memory_id="memory-candidate",
            domain="cli_workflow",
            memory_type="command_template",
            scope="project",
            source_type="shell",
            source_ref="event-2",
            content_text="npm run test",
            status="candidate",
        )

        self.store.insert_memory_core(active)
        self.store.insert_memory_core(candidate)

        rows = self.store.list_active_memories(domain="cli_workflow")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["memory_id"], "memory-active")

    def test_batch_get_memories_preserves_input_order_and_empty_list(self) -> None:
        memory_1 = MemoryCore(
            memory_id="memory-1",
            domain="cli_workflow",
            memory_type="command_template",
            scope="project",
            source_type="shell",
            source_ref="event-1",
            content_text="npm run build",
        )
        memory_2 = MemoryCore(
            memory_id="memory-2",
            domain="cli_workflow",
            memory_type="command_template",
            scope="workspace",
            source_type="shell",
            source_ref="event-2",
            content_text="npm run test",
        )
        self.store.insert_memory_core(memory_1)
        self.store.insert_memory_core(memory_2)

        rows = self.store.batch_get_memories(["memory-2", "memory-1"])

        self.assertEqual([row["memory_id"] for row in rows], ["memory-2", "memory-1"])
        self.assertEqual(self.store.batch_get_memories([]), [])

    def test_update_confidence_and_importance(self) -> None:
        memory = MemoryCore(
            memory_id="memory-1",
            domain="cli_workflow",
            memory_type="command_template",
            scope="project",
            source_type="shell",
            source_ref="event-1",
            content_text="npm run build",
            confidence=0.1,
            importance=0.2,
        )
        self.store.insert_memory_core(memory)

        self.store.update_confidence("memory-1", 0.8)
        self.store.update_importance("memory-1", 0.9)
        fetched = self.store.get_memory("memory-1")

        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched["confidence"], 0.8)
        self.assertEqual(fetched["importance"], 0.9)

    def test_search_candidates_and_scope_filter(self) -> None:
        project_memory = MemoryCore(
            memory_id="memory-project",
            domain="cli_workflow",
            memory_type="command_template",
            scope="project",
            source_type="shell",
            source_ref="event-1",
            content_text="npm run build",
        )
        workspace_memory = MemoryCore(
            memory_id="memory-workspace",
            domain="cli_workflow",
            memory_type="command_template",
            scope="workspace",
            source_type="shell",
            source_ref="event-2",
            content_text="npm run test",
            status="candidate",
        )
        self.store.insert_memory_core(project_memory)
        self.store.insert_memory_core(workspace_memory)

        active_project_rows = self.store.list_active_memories(
            domain="cli_workflow",
            scope="project",
        )
        candidate_rows = self.store.search_memory_candidates(
            domain="cli_workflow",
            status="candidate",
            source_ref="event-2",
        )

        self.assertEqual([row["memory_id"] for row in active_project_rows], ["memory-project"])
        self.assertEqual([row["memory_id"] for row in candidate_rows], ["memory-workspace"])

    def test_get_version_chain_and_delete_memory(self) -> None:
        old_memory = MemoryCore(
            memory_id="memory-old",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-1",
            content_text="Use SQLite",
            created_at="2026-04-26T10:00:00Z",
        )
        new_memory = MemoryCore(
            memory_id="memory-new",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-2",
            content_text="Use PostgreSQL",
            created_at="2026-04-26T11:00:00Z",
        )
        self.store.insert_memory_core(old_memory)
        self.store.insert_memory_core(new_memory)
        self.store.mark_superseded("memory-old", "memory-new")

        chain = self.store.get_version_chain("memory-new")
        self.store.delete_memory("memory-old")

        self.assertEqual([row["memory_id"] for row in chain], ["memory-old", "memory-new"])
        self.assertIsNone(self.store.get_memory("memory-old"))

    def test_search_bm25_finds_inserted_memory_and_filters_domain(self) -> None:
        target = MemoryCore(
            memory_id="memory-target",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-1",
            content_text="Use SQLite for local demo storage",
            summary_text="SQLite storage decision",
            entities=["project_id:project-1", "SQLite"],
            tags=["decision", "storage"],
        )
        other_domain = MemoryCore(
            memory_id="memory-other",
            domain="cli_workflow",
            memory_type="command_template",
            scope="project",
            source_type="shell",
            source_ref="event-2",
            content_text="Use SQLite command",
            summary_text="SQLite command",
            entities=["SQLite"],
            tags=["command"],
        )
        self.store.insert_memory_core(target)
        self.store.insert_memory_core(other_domain)

        rows = self.store.search_bm25("SQLite storage", domain="project_decision", limit=5)

        self.assertEqual([row["memory_id"] for row in rows], ["memory-target"])
        self.assertGreater(rows[0]["bm25_score"], 0)

    def test_search_bm25_tracks_status_updates_and_deletes(self) -> None:
        memory = MemoryCore(
            memory_id="memory-bm25-status",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-1",
            content_text="Use PostgreSQL for analytics",
            summary_text="PostgreSQL analytics decision",
        )
        self.store.insert_memory_core(memory)

        active_rows = self.store.search_bm25("PostgreSQL analytics", domain="project_decision", status="active")
        self.store.update_memory_status("memory-bm25-status", "superseded")
        superseded_rows = self.store.search_bm25(
            "PostgreSQL analytics",
            domain="project_decision",
            status="superseded",
        )
        active_after_update = self.store.search_bm25("PostgreSQL analytics", domain="project_decision", status="active")
        self.store.delete_memory("memory-bm25-status")
        after_delete = self.store.search_bm25("PostgreSQL analytics", domain="project_decision", status="superseded")

        self.assertEqual([row["memory_id"] for row in active_rows], ["memory-bm25-status"])
        self.assertEqual([row["memory_id"] for row in superseded_rows], ["memory-bm25-status"])
        self.assertEqual(active_after_update, [])
        self.assertEqual(after_delete, [])

    def test_search_bm25_returns_empty_for_blank_or_punctuation_query(self) -> None:
        memory = MemoryCore(
            memory_id="memory-empty-query",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-1",
            content_text="Use SQLite",
        )
        self.store.insert_memory_core(memory)

        self.assertEqual(self.store.search_bm25("   ", domain="project_decision"), [])
        self.assertEqual(self.store.search_bm25("???", domain="project_decision"), [])
