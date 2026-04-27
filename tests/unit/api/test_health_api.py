from __future__ import annotations

import os
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.dependencies import reset_dependency_cache
from src.app.main import create_app


class TestHealthApi(unittest.TestCase):
    def setUp(self) -> None:
        reset_dependency_cache()
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        self.temp_dir = root / f"api-health-{uuid.uuid4().hex}"
        self.temp_dir.mkdir()
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.addCleanup(reset_dependency_cache)

    def test_health_returns_dependency_status(self) -> None:
        db_path = str(self.temp_dir / "health.db")
        with patch.dict(os.environ, {"LARKMEMORY_SQLITE_PATH": db_path}, clear=True):
            reset_dependency_cache()
            client = TestClient(create_app())
            response = client.get("/health")

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["status"], "ok")
        self.assertIn("storage", body)
        self.assertIn("embedding", body)
        self.assertIn("llm", body)
        self.assertFalse(body["embedding"]["enabled"])
        self.assertFalse(body["embedding"]["available"])
        self.assertFalse(body["llm"]["enabled"])
        self.assertFalse(body["llm"]["available"])

