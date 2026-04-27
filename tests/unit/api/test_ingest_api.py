from __future__ import annotations

import os
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.dependencies import get_event_store, get_memory_core_store, reset_dependency_cache
from src.app.main import create_app


class TestIngestApi(unittest.TestCase):
    def setUp(self) -> None:
        reset_dependency_cache()
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        self.temp_dir = root / f"api-ingest-{uuid.uuid4().hex}"
        self.temp_dir.mkdir()
        self.db_path = str(self.temp_dir / "ingest.db")
        self.env = patch.dict(os.environ, {"LARKMEMORY_SQLITE_PATH": self.db_path}, clear=True)
        self.env.start()
        reset_dependency_cache()
        self.client = TestClient(create_app())
        self.addCleanup(self.env.stop)
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.addCleanup(reset_dependency_cache)

    def test_ingest_writes_event(self) -> None:
        response = self.client.post(
            "/api/v1/ingest",
            json={
                "event_id": "event-api-1",
                "event_type": "chat_message",
                "source_type": "feishu_chat",
                "occurred_at": "2026-04-27T00:00:00Z",
                "context": {"project_id": "project-1"},
                "content_text": "decide to use option B",
                "payload": {"topic": "architecture"},
            },
        )
        stored = get_event_store().get_event("event-api-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["event_id"], "event-api-1")
        self.assertTrue(response.json()["stored"])
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored["project_id"], "project-1")

    def test_ingest_project_decision_creates_memory_core(self) -> None:
        response = self.client.post(
            "/api/v1/ingest",
            json={
                "event_id": "event-decision-1",
                "event_type": "chat_message",
                "source_type": "feishu_chat",
                "occurred_at": "2026-04-27T00:00:00Z",
                "context": {"project_id": "project-1"},
                "content_text": "我们决定采用方案 B 而不是方案 A，因为接入成本更低",
            },
        )
        memories = get_memory_core_store().list_active_memories(domain="project_decision")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["memory_candidates"], 1)
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]["source_event_id"], "event-decision-1")

    def test_ingest_generates_event_id(self) -> None:
        response = self.client.post(
            "/api/v1/ingest",
            json={
                "event_type": "chat_message",
                "source_type": "feishu_chat",
                "content_text": "hello",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["event_id"].startswith("evt-"))

    def test_duplicate_event_id_returns_409(self) -> None:
        payload = {
            "event_id": "event-duplicate",
            "event_type": "chat_message",
            "source_type": "feishu_chat",
        }
        self.assertEqual(self.client.post("/api/v1/ingest", json=payload).status_code, 200)
        response = self.client.post("/api/v1/ingest", json=payload)

        self.assertEqual(response.status_code, 409)
