from __future__ import annotations

import os
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from src.app.dependencies import (
    get_embedding_store,
    get_event_store,
    get_llm_client,
    get_memory_service,
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

    def test_get_embedding_store_returns_none_when_disabled(self) -> None:
        with patch.dict(os.environ, {"LARKMEMORY_ENABLE_EMBEDDING": "false"}, clear=True):
            reset_dependency_cache()
            self.assertIsNone(get_embedding_store())

    def test_get_llm_client_returns_none_when_disabled(self) -> None:
        with patch.dict(os.environ, {"LARKMEMORY_ENABLE_LLM": "false"}, clear=True):
            reset_dependency_cache()
            self.assertIsNone(get_llm_client())

    def test_get_llm_client_returns_none_when_missing_key_or_model(self) -> None:
        with patch.dict(os.environ, {"LARKMEMORY_ENABLE_LLM": "true"}, clear=True):
            reset_dependency_cache()
            self.assertIsNone(get_llm_client())
