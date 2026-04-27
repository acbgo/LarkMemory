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


class TestRetrieveApi(unittest.TestCase):
    def setUp(self) -> None:
        reset_dependency_cache()
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        self.temp_dir = root / f"api-retrieve-{uuid.uuid4().hex}"
        self.temp_dir.mkdir()
        self.db_path = str(self.temp_dir / "retrieve.db")
        self.env = patch.dict(os.environ, {"LARKMEMORY_SQLITE_PATH": self.db_path}, clear=True)
        self.env.start()
        reset_dependency_cache()
        self.client = TestClient(create_app())
        self.addCleanup(self.env.stop)
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.addCleanup(reset_dependency_cache)

    def test_empty_retrieve_returns_empty_results(self) -> None:
        with self.assertLogs(level="INFO") as captured:
            response = self.client.post(
                "/api/v1/retrieve",
                json={"query_text": "why choose sqlite", "include_trace": True},
            )

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["results"], [])
        self.assertEqual(body["trace"]["mode"], "memory_core_fallback")
        self.assertIn(
            "function=src.api.retrieve.retrieve_memories",
            "\n".join(captured.output),
        )

    def test_retrieve_returns_active_memory_hit_and_respects_top_k(self) -> None:
        store = get_memory_core_store()
        store.insert_memory_core(
            MemoryCore(
                memory_id="memory-1",
                domain="project_decision",
                memory_type="decision",
                scope="project",
                source_type="feishu_chat",
                source_ref="event-1",
                content_text="We chose SQLite for local demo storage",
                importance=0.8,
                confidence=0.9,
                tags=["sqlite"],
            )
        )
        store.insert_memory_core(
            MemoryCore(
                memory_id="memory-2",
                domain="cli_workflow",
                memory_type="command_template",
                scope="project",
                source_type="shell",
                source_ref="event-2",
                content_text="Run pytest before commit",
                importance=0.5,
                confidence=0.7,
            )
        )

        response = self.client.post(
            "/api/v1/retrieve",
            json={"query_text": "sqlite storage", "top_k": 1},
        )

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(body["results"]), 1)
        self.assertEqual(body["results"][0]["memory_id"], "memory-1")

    def test_search_alias_is_available(self) -> None:
        response = self.client.post(
            "/api/v1/memories/search",
            json={"query_text": "anything"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("query_id", response.json())

    def test_ingest_then_retrieve_project_decision(self) -> None:
        ingest_response = self.client.post(
            "/api/v1/ingest",
            json={
                "event_id": "event-decision-retrieve",
                "event_type": "chat_message",
                "source_type": "feishu_chat",
                "occurred_at": "2026-04-27T00:00:00Z",
                "context": {"project_id": "project-1"},
                "content_text": "我们决定采用方案 B 而不是方案 A，因为接入成本更低",
            },
        )
        retrieve_response = self.client.post(
            "/api/v1/retrieve",
            json={"query_text": "方案 B", "project_id": "project-1", "top_k": 1},
        )

        self.assertEqual(ingest_response.status_code, 200)
        self.assertEqual(ingest_response.json()["memory_candidates"], 1)
        self.assertEqual(retrieve_response.status_code, 200)
        self.assertEqual(len(retrieve_response.json()["results"]), 1)
        self.assertEqual(retrieve_response.json()["results"][0]["domain"], "project_decision")
