from __future__ import annotations

import os
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.dependencies import get_memory_core_store, reset_dependency_cache
from src.app.main import create_app
from src.schemas import MemoryCore


class TestUpdateApi(unittest.TestCase):
    def setUp(self) -> None:
        reset_dependency_cache()
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        self.temp_dir = root / f"api-update-{uuid.uuid4().hex}"
        self.temp_dir.mkdir()
        self.db_path = str(self.temp_dir / "update.db")
        self.env = patch.dict(os.environ, {"LARKMEMORY_SQLITE_PATH": self.db_path}, clear=True)
        self.env.start()
        reset_dependency_cache()
        self.client = TestClient(create_app())
        self.store = get_memory_core_store()
        self.addCleanup(self.env.stop)
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.addCleanup(reset_dependency_cache)

    def _insert_memory(self, memory_id: str) -> None:
        self.store.insert_memory_core(
            MemoryCore(
                memory_id=memory_id,
                domain="project_decision",
                memory_type="decision",
                scope="project",
                source_type="feishu_chat",
                source_ref=f"event-{memory_id}",
                content_text=f"content {memory_id}",
            )
        )

    def test_expire_and_forget_update_status(self) -> None:
        self._insert_memory("memory-expire")
        response = self.client.post(
            "/api/v1/update",
            json={"action": "expire", "memory_id": "memory-expire"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.store.get_memory("memory-expire")["status"], "expired")

        self._insert_memory("memory-forget")
        response = self.client.post(
            "/api/v1/update",
            json={"action": "forget", "memory_id": "memory-forget"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.store.get_memory("memory-forget")["status"], "forgotten")

    def test_confidence_and_importance_update_fields(self) -> None:
        self._insert_memory("memory-score")
        self.assertEqual(
            self.client.post(
                "/api/v1/update",
                json={
                    "action": "confidence",
                    "memory_id": "memory-score",
                    "confidence": 0.77,
                },
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/update",
                json={
                    "action": "importance",
                    "memory_id": "memory-score",
                    "importance": 0.88,
                },
            ).status_code,
            200,
        )
        row = self.store.get_memory("memory-score")
        self.assertEqual(row["confidence"], 0.77)
        self.assertEqual(row["importance"], 0.88)

    def test_supersede_links_memories(self) -> None:
        self._insert_memory("memory-old")
        self._insert_memory("memory-new")
        response = self.client.post(
            "/api/v1/update",
            json={
                "action": "supersede",
                "memory_id": "memory-old",
                "new_memory_id": "memory-new",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.store.get_memory("memory-old")["status"], "superseded")
        self.assertEqual(self.store.get_memory("memory-old")["superseded_by"], "memory-new")
        self.assertEqual(self.store.get_memory("memory-new")["overwrite_of"], "memory-old")

    def test_feedback_returns_accepted_and_alias_works(self) -> None:
        response = self.client.post(
            "/api/v1/memories/update",
            json={"action": "feedback", "feedback_signal": "useful"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "accepted")
        self.assertFalse(response.json()["updated"])

    def test_missing_required_field_returns_400(self) -> None:
        response = self.client.post("/api/v1/update", json={"action": "expire"})

        self.assertEqual(response.status_code, 400)

