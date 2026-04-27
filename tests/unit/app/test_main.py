from __future__ import annotations

import unittest
import os
import shutil
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.app.config import AppSettings
from src.app.main import create_app, register_routers


class TestMain(unittest.TestCase):
    def setUp(self) -> None:
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        self.temp_dir = root / f"app-main-{uuid.uuid4().hex}"
        self.temp_dir.mkdir()
        self.addCleanup(shutil.rmtree, self.temp_dir, True)

    def test_create_app_returns_fastapi_and_stores_settings(self) -> None:
        settings = AppSettings(app_name="Test Engine", env="test")
        app = create_app(settings)

        self.assertIsInstance(app, FastAPI)
        self.assertIs(app.state.settings, settings)

    def test_create_app_registers_health_api_route(self) -> None:
        db_path = str(self.temp_dir / "health.db")
        with patch.dict(os.environ, {"LARKMEMORY_SQLITE_PATH": db_path}, clear=True):
            app = create_app(AppSettings())
            client = TestClient(app)

            response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertIn("storage", response.json())

    def test_register_routers_skips_missing_api_package(self) -> None:
        app = FastAPI()

        with patch("src.app.main.ROUTER_MODULES", ["src.api.missing"]):
            self.assertEqual(register_routers(app), [])

    def test_register_routers_registers_existing_api_modules(self) -> None:
        app = FastAPI()

        registered = register_routers(app)

        self.assertIn("health", registered)
        self.assertIn("ingest", registered)
        self.assertIn("retrieve", registered)

    def test_request_log_middleware_adds_request_id_header(self) -> None:
        db_path = str(self.temp_dir / "main.db")
        with patch.dict(os.environ, {"LARKMEMORY_SQLITE_PATH": db_path}, clear=True):
            app = create_app(AppSettings(request_log_enabled=True))
            client = TestClient(app)

            response = client.get("/health", headers={"x-request-id": "req-main"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-request-id"], "req-main")
