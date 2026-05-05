from __future__ import annotations

import unittest
import os
import shutil
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.dependencies import reset_dependency_cache
from src.app.main import create_app


class TestProactiveApi(unittest.TestCase):
    def setUp(self) -> None:
        reset_dependency_cache()
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        self.temp_dir = root / f"api-proactive-{uuid.uuid4().hex}"
        self.temp_dir.mkdir()
        self.db_path = str(self.temp_dir / "proactive.db")
        self.env = patch.dict(
            os.environ,
            {
                "LARKMEMORY_SQLITE_PATH": self.db_path,
                "LARKMEMORY_CONFIG_FILE": str(self.temp_dir / "missing.env"),
            },
            clear=True,
        )
        self.env.start()
        reset_dependency_cache()
        self.addCleanup(reset_dependency_cache)
        self.addCleanup(self.env.stop)
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.client = TestClient(create_app())

    def test_proactive_returns_empty_fallback(self) -> None:
        response = self.client.get("/api/v1/proactive")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["suggestions"], [])
        self.assertEqual(response.json()["status"], "ok")

    def test_proactive_accepts_context_query_params(self) -> None:
        response = self.client.get(
            "/api/v1/proactive",
            params={"user_id": "u1", "project_id": "p1", "team_id": "t1", "limit": 5},
        )

        self.assertEqual(response.status_code, 200)

    def test_proactive_returns_due_team_retention_review(self) -> None:
        ingest = self.client.post(
            "/api/v1/ingest",
            json={
                "event_id": "event-retention-api",
                "event_type": "chat_message",
                "source_type": "feishu_chat",
                "occurred_at": "2026-04-27T00:00:00Z",
                "context": {"team_id": "team-1", "project_id": "project-1"},
                "content_text": "请团队长期记住：API key 已更新到 secret-v2，旧 key 不再使用。",
            },
        )
        response = self.client.get(
            "/api/v1/proactive",
            params={"team_id": "team-1", "now": "2026-04-28T00:00:00Z"},
        )

        self.assertEqual(ingest.status_code, 200)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["suggestions"]), 1)
        self.assertEqual(response.json()["suggestions"][0]["type"], "review_reminder")

    def test_proactive_invalid_limit_returns_422(self) -> None:
        response = self.client.get("/api/v1/proactive", params={"limit": 0})

        self.assertEqual(response.status_code, 422)

