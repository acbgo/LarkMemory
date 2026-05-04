from __future__ import annotations

import os
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from src.app.dependencies import (
    get_embedding_client,
    get_embedding_store,
    get_event_store,
    get_llm_client,
    get_memory_service,
    get_rerank_client,
    get_memory_core_store,
    get_settings,
    reset_dependency_cache,
)


class TestDependencies(unittest.TestCase):
    def setUp(self) -> None:
        reset_dependency_cache()
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        self.temp_dir = root / f"app-dependencies-{uuid.uuid4().hex}"
        self.temp_dir.mkdir()
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.addCleanup(reset_dependency_cache)

    def test_get_settings_returns_cached_object(self) -> None:
        db_path = str(self.temp_dir / "one.db")
        with patch.dict(os.environ, {"LARKMEMORY_SQLITE_PATH": db_path}, clear=True):
            first = get_settings()
            second = get_settings()

        self.assertIs(first, second)
        self.assertEqual(first.sqlite_path, db_path)

    def test_reset_dependency_cache_reloads_settings(self) -> None:
        first_db = str(self.temp_dir / "one.db")
        second_db = str(self.temp_dir / "two.db")

        with patch.dict(os.environ, {"LARKMEMORY_SQLITE_PATH": first_db}, clear=True):
            first = get_settings()
        with patch.dict(os.environ, {"LARKMEMORY_SQLITE_PATH": second_db}, clear=True):
            reset_dependency_cache()
            second = get_settings()

        self.assertNotEqual(first.sqlite_path, second.sqlite_path)
        self.assertEqual(second.sqlite_path, second_db)

    def test_get_event_store_creates_table(self) -> None:
        db_path = str(self.temp_dir / "events.db")
        with patch.dict(os.environ, {"LARKMEMORY_SQLITE_PATH": db_path}, clear=True):
            reset_dependency_cache()
            store = get_event_store()
            row = store.fetch_one(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
                ("event_store",),
            )

        self.assertIsNotNone(row)

    def test_get_memory_core_store_creates_table(self) -> None:
        db_path = str(self.temp_dir / "memory.db")
        with patch.dict(os.environ, {"LARKMEMORY_SQLITE_PATH": db_path}, clear=True):
            reset_dependency_cache()
            store = get_memory_core_store()
            row = store.fetch_one(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
                ("memory_core",),
            )

        self.assertIsNotNone(row)

    def test_get_memory_service_uses_cached_stores(self) -> None:
        db_path = str(self.temp_dir / "service.db")
        with patch.dict(os.environ, {"LARKMEMORY_SQLITE_PATH": db_path}, clear=True):
            reset_dependency_cache()
            service = get_memory_service()

        self.assertIs(service.event_store, get_event_store())
        self.assertIs(service.memory_store, get_memory_core_store())

    def test_get_memory_service_wires_embedding_store_to_team_retention_retriever(self) -> None:
        db_path = str(self.temp_dir / "service-embedding.db")
        fake_embedding = object()
        with patch.dict(os.environ, {"LARKMEMORY_SQLITE_PATH": db_path}, clear=True):
            reset_dependency_cache()
            with patch("src.app.dependencies.get_embedding_store", return_value=fake_embedding):
                service = get_memory_service()

        team_handler = service.domain_handlers["team_retention"]
        self.assertIs(team_handler.retriever.embedding_store, fake_embedding)

    def test_get_memory_service_wires_embedding_store_to_project_decision_handler(self) -> None:
        db_path = str(self.temp_dir / "service-project-embedding.db")
        fake_embedding = object()
        with patch.dict(os.environ, {"LARKMEMORY_SQLITE_PATH": db_path}, clear=True):
            reset_dependency_cache()
            with patch("src.app.dependencies.get_embedding_store", return_value=fake_embedding):
                service = get_memory_service()

        project_handler = service.domain_handlers["project_decision"]
        self.assertIs(project_handler.embedding_store, fake_embedding)

    def test_get_embedding_store_returns_none_when_disabled(self) -> None:
        with patch.dict(os.environ, {"LARKMEMORY_ENABLE_EMBEDDING": "false"}, clear=True):
            reset_dependency_cache()
            self.assertIsNone(get_embedding_store())

    def test_get_embedding_client_returns_none_when_disabled(self) -> None:
        with patch.dict(os.environ, {"LARKMEMORY_ENABLE_EMBEDDING": "false"}, clear=True):
            reset_dependency_cache()
            self.assertIsNone(get_embedding_client())

    def test_get_embedding_client_builds_openai_compatible_client(self) -> None:
        db_path = str(self.temp_dir / "embedding-client.db")
        with patch.dict(
            os.environ,
            {
                "LARKMEMORY_SQLITE_PATH": db_path,
                "LARKMEMORY_ENABLE_EMBEDDING": "true",
                "LARKMEMORY_EMBEDDING_API_KEY": "test-key",
                "LARKMEMORY_EMBEDDING_MODEL": "Qwen/Qwen3-Embedding-4B",
                "LARKMEMORY_EMBEDDING_BASE_URL": "https://api.siliconflow.cn/v1",
                "LARKMEMORY_EMBEDDING_DIMENSIONS": "1024",
            },
            clear=True,
        ):
            reset_dependency_cache()
            with patch("src.app.dependencies.OpenAICompatibleEmbeddingProvider") as provider_cls:
                client = get_embedding_client()

        self.assertIsNotNone(client)
        provider_cls.assert_called_once()
        self.assertEqual(provider_cls.call_args.kwargs["model"], "Qwen/Qwen3-Embedding-4B")
        self.assertEqual(provider_cls.call_args.kwargs["dimensions"], 1024)

    def test_get_embedding_client_accepts_http_provider_alias(self) -> None:
        db_path = str(self.temp_dir / "embedding-http-client.db")
        with patch.dict(
            os.environ,
            {
                "LARKMEMORY_SQLITE_PATH": db_path,
                "LARKMEMORY_ENABLE_EMBEDDING": "true",
                "LARKMEMORY_EMBEDDING_PROVIDER": "http",
                "LARKMEMORY_EMBEDDING_API_KEY": "test-key",
                "LARKMEMORY_EMBEDDING_MODEL": "Qwen/Qwen3-Embedding-4B",
                "LARKMEMORY_EMBEDDING_BASE_URL": "http://127.0.0.1:8001/v1",
            },
            clear=True,
        ):
            reset_dependency_cache()
            with patch("src.app.dependencies.OpenAICompatibleEmbeddingProvider") as provider_cls:
                client = get_embedding_client()

        self.assertIsNotNone(client)
        provider_cls.assert_called_once()
        self.assertEqual(provider_cls.call_args.kwargs["base_url"], "http://127.0.0.1:8001/v1")

    def test_get_embedding_client_builds_local_sentence_transformers_client(self) -> None:
        db_path = str(self.temp_dir / "local-embedding-client.db")
        with patch.dict(
            os.environ,
            {
                "LARKMEMORY_SQLITE_PATH": db_path,
                "LARKMEMORY_ENABLE_EMBEDDING": "true",
                "LARKMEMORY_EMBEDDING_PROVIDER": "local_sentence_transformers",
                "LARKMEMORY_EMBEDDING_MODEL_PATH": ".larkmemory/models/Qwen/Qwen3-Embedding-4B",
                "LARKMEMORY_EMBEDDING_DEVICE": "cpu",
                "LARKMEMORY_EMBEDDING_NORMALIZE": "true",
                "LARKMEMORY_EMBEDDING_BATCH_SIZE": "4",
                "LARKMEMORY_EMBEDDING_DIMENSIONS": "1024",
                "LARKMEMORY_EMBEDDING_TRUST_REMOTE_CODE": "true",
            },
            clear=True,
        ):
            reset_dependency_cache()
            with patch("src.app.dependencies.LocalSentenceTransformersEmbeddingProvider") as provider_cls:
                client = get_embedding_client()

        self.assertIsNotNone(client)
        provider_cls.assert_called_once()
        self.assertEqual(
            provider_cls.call_args.kwargs["model_path"],
            ".larkmemory/models/Qwen/Qwen3-Embedding-4B",
        )
        self.assertEqual(provider_cls.call_args.kwargs["device"], "cpu")
        self.assertTrue(provider_cls.call_args.kwargs["normalize_embeddings"])
        self.assertEqual(provider_cls.call_args.kwargs["batch_size"], 4)
        self.assertEqual(provider_cls.call_args.kwargs["dimensions"], 1024)
        self.assertTrue(provider_cls.call_args.kwargs["trust_remote_code"])

    def test_get_embedding_client_returns_none_when_provider_init_fails(self) -> None:
        db_path = str(self.temp_dir / "embedding-client-failed.db")
        with patch.dict(
            os.environ,
            {
                "LARKMEMORY_SQLITE_PATH": db_path,
                "LARKMEMORY_ENABLE_EMBEDDING": "true",
                "LARKMEMORY_EMBEDDING_PROVIDER": "local_sentence_transformers",
                "LARKMEMORY_EMBEDDING_MODEL_PATH": ".larkmemory/models/missing",
            },
            clear=True,
        ):
            reset_dependency_cache()
            with patch(
                "src.app.dependencies.LocalSentenceTransformersEmbeddingProvider",
                side_effect=ImportError("Missing dependency: sentence-transformers"),
            ):
                self.assertIsNone(get_embedding_client())

    def test_get_rerank_client_builds_http_client(self) -> None:
        db_path = str(self.temp_dir / "rerank-client.db")
        with patch.dict(
            os.environ,
            {
                "LARKMEMORY_SQLITE_PATH": db_path,
                "LARKMEMORY_ENABLE_RERANK": "true",
                "LARKMEMORY_RERANK_PROVIDER": "http",
                "LARKMEMORY_RERANK_BASE_URL": "http://127.0.0.1:9000",
                "LARKMEMORY_RERANK_ENDPOINT": "/rerank",
                "LARKMEMORY_RERANK_MODEL": "bge-reranker-v2-m3",
                "LARKMEMORY_RERANK_API_KEY": "test-key",
            },
            clear=True,
        ):
            reset_dependency_cache()
            with patch("src.app.dependencies.HttpRerankProvider") as provider_cls:
                client = get_rerank_client()

        self.assertIsNotNone(client)
        provider_cls.assert_called_once()
        self.assertEqual(provider_cls.call_args.kwargs["base_url"], "http://127.0.0.1:9000")
        self.assertEqual(provider_cls.call_args.kwargs["endpoint_path"], "/rerank")
        self.assertEqual(provider_cls.call_args.kwargs["model"], "bge-reranker-v2-m3")

    def test_get_rerank_client_returns_none_when_disabled_or_unconfigured(self) -> None:
        with patch.dict(os.environ, {"LARKMEMORY_ENABLE_RERANK": "false"}, clear=True):
            reset_dependency_cache()
            self.assertIsNone(get_rerank_client())

        with patch.dict(
            os.environ,
            {
                "LARKMEMORY_ENABLE_RERANK": "true",
                "LARKMEMORY_CONFIG_FILE": str(self.temp_dir / "missing.env"),
            },
            clear=True,
        ):
            reset_dependency_cache()
            self.assertIsNone(get_rerank_client())

    def test_get_llm_client_returns_none_when_disabled(self) -> None:
        with patch.dict(os.environ, {"LARKMEMORY_ENABLE_LLM": "false"}, clear=True):
            reset_dependency_cache()
            self.assertIsNone(get_llm_client())

    def test_get_llm_client_returns_none_when_missing_key_or_model(self) -> None:
        with patch.dict(os.environ, {"LARKMEMORY_ENABLE_LLM": "true"}, clear=True):
            reset_dependency_cache()
            self.assertIsNone(get_llm_client())
