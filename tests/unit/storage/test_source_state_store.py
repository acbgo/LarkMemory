from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from src.storage.source_state_store import SourceStateStore


class TestSourceStateStore(unittest.TestCase):
    def setUp(self) -> None:
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        self.temp_dir = root / f"source-state-{uuid.uuid4().hex}"
        self.temp_dir.mkdir()
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.db_path = str(self.temp_dir / "test.db")
        self.store = SourceStateStore(self.db_path)
        self.store.create_table()

    # ----- upsert & get -----

    def test_upsert_and_get(self) -> None:
        self.store.upsert_state("feishu_vc", "meeting-1", status="pending", last_hash="abc123")
        state = self.store.get_state("feishu_vc", "meeting-1")
        self.assertIsNotNone(state)
        assert state is not None
        self.assertEqual(state["status"], "pending")
        self.assertEqual(state["last_hash"], "abc123")

    def test_upsert_updates_existing(self) -> None:
        self.store.upsert_state("feishu_vc", "meeting-1", status="pending")
        self.store.upsert_state("feishu_vc", "meeting-1", status="complete", last_hash="xyz")
        state = self.store.get_state("feishu_vc", "meeting-1")
        self.assertEqual(state["status"], "complete")
        self.assertEqual(state["last_hash"], "xyz")

    def test_upsert_coalesce_preserves_hash_when_none(self) -> None:
        self.store.upsert_state("feishu_doc", "doc-1", status="pending", last_hash="doc-hash-1")
        self.store.upsert_state("feishu_doc", "doc-1", status="partial", last_hash=None)
        state = self.store.get_state("feishu_doc", "doc-1")
        self.assertEqual(state["last_hash"], "doc-hash-1")

    def test_get_nonexistent(self) -> None:
        self.assertIsNone(self.store.get_state("feishu_vc", "no-such-id"))

    def test_upsert_stores_metadata(self) -> None:
        self.store.upsert_state("feishu_vc", "meeting-1", metadata={"chapter_count": 5, "minute_token": "obc123"})
        state = self.store.get_state("feishu_vc", "meeting-1")
        self.assertEqual(state["metadata"]["chapter_count"], 5)
        self.assertEqual(state["metadata"]["minute_token"], "obc123")

    # ----- list queries -----

    def test_list_pending_returns_pending_and_partial_and_error(self) -> None:
        self.store.upsert_state("feishu_vc", "m1", status="pending")
        self.store.upsert_state("feishu_vc", "m2", status="complete")
        self.store.upsert_state("feishu_vc", "m3", status="partial")
        self.store.upsert_state("feishu_vc", "m4", status="error")
        self.store.upsert_state("feishu_vc", "m5", status="pending_ai")
        pending = self.store.list_pending("feishu_vc")
        pending_ids = {p["external_id"] for p in pending}
        self.assertIn("m1", pending_ids)
        self.assertIn("m3", pending_ids)
        self.assertIn("m4", pending_ids)
        self.assertIn("m5", pending_ids)
        self.assertNotIn("m2", pending_ids)

    def test_list_by_status_filters_correctly(self) -> None:
        self.store.upsert_state("feishu_vc", "m1", status="complete")
        self.store.upsert_state("feishu_vc", "m2", status="complete")
        self.store.upsert_state("feishu_vc", "m3", status="pending")
        complete = self.store.list_by_status("feishu_vc", "complete")
        self.assertEqual(len(complete), 2)

    def test_list_pending_respects_limit(self) -> None:
        for i in range(5):
            self.store.upsert_state("feishu_vc", f"m{i}", status="pending")
        result = self.store.list_pending("feishu_vc", limit=3)
        self.assertEqual(len(result), 3)

    def test_list_pending_orders_by_oldest_first(self) -> None:
        self.store.upsert_state("feishu_vc", "m-old", status="pending")
        self.store.upsert_state("feishu_vc", "m-new", status="pending")
        pending = self.store.list_pending("feishu_vc")
        # 先插入的应该排在前面
        self.assertEqual(pending[0]["external_id"], "m-old")

    # ----- status updates -----

    def test_mark_complete(self) -> None:
        self.store.upsert_state("feishu_vc", "meeting-1", status="pending")
        self.store.mark_complete("feishu_vc", "meeting-1")
        state = self.store.get_state("feishu_vc", "meeting-1")
        self.assertEqual(state["status"], "complete")
        self.assertTrue(state["processed_at"])

    def test_mark_error(self) -> None:
        self.store.upsert_state("feishu_vc", "meeting-1", status="pending")
        self.store.mark_error("feishu_vc", "meeting-1")
        state = self.store.get_state("feishu_vc", "meeting-1")
        self.assertEqual(state["status"], "error")
        self.assertEqual(state["error_count"], 1)
        self.store.mark_error("feishu_vc", "meeting-1")
        self.assertEqual(self.store.get_state("feishu_vc", "meeting-1")["error_count"], 2)

    def test_reset_error(self) -> None:
        self.store.upsert_state("feishu_vc", "meeting-1", status="pending")
        self.store.mark_error("feishu_vc", "meeting-1")
        self.store.mark_error("feishu_vc", "meeting-1")
        self.assertEqual(self.store.get_state("feishu_vc", "meeting-1")["error_count"], 2)
        self.store.reset_error("feishu_vc", "meeting-1")
        self.assertEqual(self.store.get_state("feishu_vc", "meeting-1")["error_count"], 0)

    def test_upsert_resets_error_count(self) -> None:
        self.store.upsert_state("feishu_vc", "meeting-1", status="pending")
        self.store.mark_error("feishu_vc", "meeting-1")
        self.store.mark_error("feishu_vc", "meeting-1")
        self.assertEqual(self.store.get_state("feishu_vc", "meeting-1")["error_count"], 2)
        # 重新 upsert 应重置 error_count
        self.store.upsert_state("feishu_vc", "meeting-1", status="pending")
        self.assertEqual(self.store.get_state("feishu_vc", "meeting-1")["error_count"], 0)

    def test_upsert_empty_string_overwrites_hash(self) -> None:
        self.store.upsert_state("feishu_doc", "doc-1", last_hash="original-hash")
        self.assertEqual(self.store.get_state("feishu_doc", "doc-1")["last_hash"], "original-hash")
        # 空字符串不是 NULL，应覆盖旧值
        self.store.upsert_state("feishu_doc", "doc-1", last_hash="")
        self.assertEqual(self.store.get_state("feishu_doc", "doc-1")["last_hash"], "")

    def test_upsert_none_preserves_hash(self) -> None:
        self.store.upsert_state("feishu_doc", "doc-1", last_hash="original-hash")
        # None 应被 COALESCE 保留旧值
        self.store.upsert_state("feishu_doc", "doc-1", last_hash=None)
        self.assertEqual(self.store.get_state("feishu_doc", "doc-1")["last_hash"], "original-hash")

    def test_update_cursor(self) -> None:
        self.store.upsert_state("feishu_vc", "scanner", status="scanning")
        self.store.update_cursor("feishu_vc", "scanner", "2026-05-04T12:00:00Z")
        state = self.store.get_state("feishu_vc", "scanner")
        self.assertEqual(state["cursor_value"], "2026-05-04T12:00:00Z")

    def test_update_hash(self) -> None:
        self.store.upsert_state("feishu_doc", "doc-1", status="pending", last_hash="old-hash")
        self.store.update_hash("feishu_doc", "doc-1", "new-hash")
        state = self.store.get_state("feishu_doc", "doc-1")
        self.assertEqual(state["last_hash"], "new-hash")

    # ----- multi-source isolation -----

    def test_different_source_types_isolation(self) -> None:
        self.store.upsert_state("feishu_vc", "m1", status="pending")
        self.store.upsert_state("feishu_doc", "m1", status="complete")
        self.assertEqual(self.store.get_state("feishu_vc", "m1")["status"], "pending")
        self.assertEqual(self.store.get_state("feishu_doc", "m1")["status"], "complete")

    # ----- delete -----

    def test_delete_states_before(self) -> None:
        import sqlite3
        self.store.upsert_state("feishu_vc", "old-1", status="complete")
        self.store.upsert_state("feishu_vc", "old-2", status="complete")
        # 手动把 processed_at 改成 60 天前
        with self.store.get_connection() as conn:
            conn.execute(
                "UPDATE source_processed SET processed_at = datetime('now', '-60 days') "
                "WHERE external_id IN ('old-1', 'old-2')"
            )
            conn.commit()
        deleted = self.store.delete_states_before(before_days=30)
        self.assertEqual(deleted, 2)
        self.assertIsNone(self.store.get_state("feishu_vc", "old-1"))

    def test_no_error_count_before_any_error(self) -> None:
        self.store.upsert_state("feishu_vc", "fresh", status="pending")
        state = self.store.get_state("feishu_vc", "fresh")
        self.assertEqual(state["error_count"], 0)
