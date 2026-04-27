from __future__ import annotations

import logging
import shutil
import unittest
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.app.logging import RequestLogMiddleware, get_request_id, setup_logging


class TestLogging(unittest.TestCase):
    def setUp(self) -> None:
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        self.temp_dir = root / f"app-logging-{uuid.uuid4().hex}"
        self.temp_dir.mkdir()
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.addCleanup(self._close_larkmemory_handlers)

    def _close_larkmemory_handlers(self) -> None:
        root_logger = logging.getLogger()
        for handler in list(root_logger.handlers):
            if getattr(handler, "_larkmemory_handler", False) or getattr(
                handler,
                "_larkmemory_file_handler",
                False,
            ):
                root_logger.removeHandler(handler)
                handler.close()

    def test_get_request_id_reads_x_request_id(self) -> None:
        self.assertEqual(get_request_id({"x-request-id": " req-1 "}), "req-1")

    def test_get_request_id_reads_larkmemory_request_id(self) -> None:
        self.assertEqual(
            get_request_id({"x-larkmemory-request-id": " req-2 "}),
            "req-2",
        )

    def test_get_request_id_generates_when_missing(self) -> None:
        request_id = get_request_id({})

        self.assertTrue(request_id.startswith("req-"))
        self.assertEqual(len(request_id), len("req-") + 12)

    def test_setup_logging_does_not_duplicate_larkmemory_handler(self) -> None:
        root_logger = logging.getLogger()
        before_handlers = [
            handler
            for handler in root_logger.handlers
            if getattr(handler, "_larkmemory_handler", False)
        ]

        setup_logging("INFO")
        setup_logging("DEBUG")

        after_handlers = [
            handler
            for handler in root_logger.handlers
            if getattr(handler, "_larkmemory_handler", False)
        ]
        expected_count = max(1, len(before_handlers))
        self.assertEqual(len(after_handlers), expected_count)

    def test_setup_logging_writes_file_log(self) -> None:
        setup_logging("INFO", self.temp_dir, "service.log")

        logging.getLogger("larkmemory.test").info("file log ready")
        for handler in logging.getLogger().handlers:
            handler.flush()

        log_path = self.temp_dir / "service.log"
        self.assertTrue(log_path.exists())
        self.assertIn("file log ready", log_path.read_text(encoding="utf-8"))

    def test_request_log_middleware_writes_request_id_header(self) -> None:
        app = FastAPI()
        app.add_middleware(RequestLogMiddleware)

        @app.get("/ping")
        def ping() -> dict[str, str]:
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/ping", headers={"x-request-id": "req-test"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-request-id"], "req-test")
