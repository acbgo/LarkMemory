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
from src.llm.rerank_base import RerankResponse, RerankResult


class FakeRerankClient:
    def rerank(self, query: str, documents: list[object], *, top_k: int | None = None) -> RerankResponse:
        return RerankResponse(
            model="fake-reranker",
            results=[
                RerankResult(
                    id="mem-2",
                    text="客户 A 要求 xlsx",
                    score=0.9,
                    rank=1,
                    index=1,
                    metadata={"domain": "team_retention"},
                )
            ],
        )


class RaisingRerankClient:
    def rerank(self, *args: object, **kwargs: object) -> RerankResponse:
        raise RuntimeError("rerank upstream timeout")


class TestRerankApi(unittest.TestCase):
    def setUp(self) -> None:
        reset_dependency_cache()
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        self.temp_dir = root / f"api-rerank-{uuid.uuid4().hex}"
        self.temp_dir.mkdir()
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.addCleanup(reset_dependency_cache)

    def test_rerank_api_returns_ranked_documents(self) -> None:
        db_path = str(self.temp_dir / "rerank.db")
        with patch.dict(os.environ, {"LARKMEMORY_SQLITE_PATH": db_path}, clear=True):
            reset_dependency_cache()
            app = create_app()
            from src.app.dependencies import get_rerank_client

            app.dependency_overrides[get_rerank_client] = lambda: FakeRerankClient()
            client = TestClient(app)
            response = client.post(
                "/api/v1/rerank",
                json={
                    "query": "客户 A 导出格式",
                    "documents": [
                        {"id": "mem-1", "text": "客户 B 偏好 PDF"},
                        {
                            "id": "mem-2",
                            "text": "客户 A 要求 xlsx",
                            "metadata": {"domain": "team_retention"},
                        },
                    ],
                    "top_k": 1,
                },
            )

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["model"], "fake-reranker")
        self.assertEqual(body["results"][0]["id"], "mem-2")
        self.assertEqual(body["results"][0]["score"], 0.9)

    def test_rerank_api_returns_503_when_client_unavailable(self) -> None:
        db_path = str(self.temp_dir / "rerank-disabled.db")
        with patch.dict(os.environ, {"LARKMEMORY_SQLITE_PATH": db_path}, clear=True):
            reset_dependency_cache()
            client = TestClient(create_app())
            response = client.post(
                "/api/v1/rerank",
                json={"query": "q", "documents": [{"id": "d1", "text": "doc"}]},
            )

        self.assertEqual(response.status_code, 503)

    def test_rerank_api_maps_upstream_failure_to_502(self) -> None:
        db_path = str(self.temp_dir / "rerank-upstream-failed.db")
        with patch.dict(os.environ, {"LARKMEMORY_SQLITE_PATH": db_path}, clear=True):
            reset_dependency_cache()
            app = create_app()
            from src.app.dependencies import get_rerank_client

            app.dependency_overrides[get_rerank_client] = lambda: RaisingRerankClient()
            client = TestClient(app)
            response = client.post(
                "/api/v1/rerank",
                json={"query": "q", "documents": [{"id": "d1", "text": "doc"}]},
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "rerank upstream failed")
