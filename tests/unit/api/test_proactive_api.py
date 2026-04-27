from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from src.app.dependencies import reset_dependency_cache
from src.app.main import create_app


class TestProactiveApi(unittest.TestCase):
    def setUp(self) -> None:
        reset_dependency_cache()
        self.addCleanup(reset_dependency_cache)
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

    def test_proactive_invalid_limit_returns_422(self) -> None:
        response = self.client.get("/api/v1/proactive", params={"limit": 0})

        self.assertEqual(response.status_code, 422)

