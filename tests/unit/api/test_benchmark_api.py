from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from src.app.dependencies import reset_dependency_cache
from src.app.main import create_app


class TestBenchmarkApi(unittest.TestCase):
    def setUp(self) -> None:
        reset_dependency_cache()
        self.addCleanup(reset_dependency_cache)
        self.client = TestClient(create_app())

    def test_dry_run_benchmark_returns_accepted(self) -> None:
        response = self.client.post(
            "/api/v1/benchmark/run",
            json={"suite_name": "memory", "dry_run": True},
        )

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["status"], "accepted")
        self.assertTrue(body["accepted"])
        self.assertTrue(body["run_id"].startswith("bench-"))

    def test_non_dry_run_returns_not_implemented(self) -> None:
        response = self.client.post(
            "/api/v1/benchmark/run",
            json={"suite_name": "memory", "dry_run": False},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "not_implemented")
        self.assertFalse(response.json()["accepted"])

    def test_get_benchmark_status_returns_not_found(self) -> None:
        response = self.client.get("/api/v1/benchmark/bench-missing")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "not_found")

