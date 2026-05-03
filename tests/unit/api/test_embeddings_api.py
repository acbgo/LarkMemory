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
from src.llm.embedding_base import EmbeddingResponse


class FakeEmbeddingClient:
    def embed_text(self, text: str) -> list[float]:
        return [0.1, 0.2]

    def embed_texts(self, texts: list[str]) -> EmbeddingResponse:
        return EmbeddingResponse(
            model="fake-embedding",
            embeddings=[[float(index), 0.5] for index, _ in enumerate(texts)],
            dimensions=2,
            usage={"total_tokens": len(texts)},
        )


class TestEmbeddingsApi(unittest.TestCase):
    def setUp(self) -> None:
        reset_dependency_cache()
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        self.temp_dir = root / f"api-embeddings-{uuid.uuid4().hex}"
        self.temp_dir.mkdir()
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.addCleanup(reset_dependency_cache)

    def test_embed_text_returns_vector(self) -> None:
        db_path = str(self.temp_dir / "embeddings.db")
        with patch.dict(os.environ, {"LARKMEMORY_SQLITE_PATH": db_path}, clear=True):
            reset_dependency_cache()
            app = create_app()
            from src.app.dependencies import get_embedding_client

            app.dependency_overrides[get_embedding_client] = lambda: FakeEmbeddingClient()
            client = TestClient(app)
            response = client.post("/api/v1/embeddings", json={"text": "客户偏好"})

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["model"], "fake-embedding")
        self.assertEqual(body["dimension"], 2)
        self.assertEqual(body["embedding"], [0.0, 0.5])
        self.assertEqual(body["usage"], {"total_tokens": 1})

    def test_embed_text_returns_503_when_client_unavailable(self) -> None:
        db_path = str(self.temp_dir / "embeddings-disabled.db")
        with patch.dict(os.environ, {"LARKMEMORY_SQLITE_PATH": db_path}, clear=True):
            reset_dependency_cache()
            client = TestClient(create_app())
            response = client.post("/api/v1/embeddings", json={"text": "客户偏好"})

        self.assertEqual(response.status_code, 503)
