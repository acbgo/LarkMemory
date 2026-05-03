from __future__ import annotations

import os
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from src.app.config import _env_bool, _env_float, _env_int, load_settings


class TestConfig(unittest.TestCase):
    def _temp_dir(self) -> Path:
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        temp_dir = root / f"app-config-{uuid.uuid4().hex}"
        temp_dir.mkdir()
        self.addCleanup(shutil.rmtree, temp_dir, True)
        return temp_dir

    def test_load_settings_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = load_settings()

        self.assertEqual(settings.app_name, "LarkMemory Engine")
        self.assertEqual(settings.env, "local")
        self.assertEqual(settings.host, "127.0.0.1")
        self.assertEqual(settings.port, 8765)
        self.assertFalse(settings.debug)
        self.assertEqual(settings.sqlite_path, ".larkmemory/larkmemory.db")
        self.assertFalse(settings.enable_llm)
        self.assertFalse(settings.enable_embedding)
        self.assertEqual(settings.log_dir, "logs")
        self.assertEqual(settings.log_file, "larkmemory.log")

    def test_load_settings_reads_environment_overrides(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LARKMEMORY_PORT": "9000",
                "LARKMEMORY_DEBUG": "true",
                "LARKMEMORY_SQLITE_PATH": ".tmp-tests/app.db",
                "LARKMEMORY_LOG_DIR": ".tmp-tests/logs",
                "LARKMEMORY_LOG_FILE": "service.log",
            },
            clear=True,
        ):
            settings = load_settings()

        self.assertEqual(settings.port, 9000)
        self.assertTrue(settings.debug)
        self.assertEqual(settings.sqlite_path, ".tmp-tests/app.db")
        self.assertEqual(settings.log_dir, ".tmp-tests/logs")
        self.assertEqual(settings.log_file, "service.log")

    def test_load_settings_reads_env_file_from_config_path(self) -> None:
        config_path = self._temp_dir() / "larkmemory.env"
        config_path.write_text(
            "\n".join(
                [
                    "# local runtime config",
                    "LARKMEMORY_PORT=9010",
                    "LARKMEMORY_ENABLE_EMBEDDING=true",
                    "LARKMEMORY_EMBEDDING_PROVIDER=http",
                    "LARKMEMORY_EMBEDDING_BASE_URL=http://127.0.0.1:8001/v1",
                    "LARKMEMORY_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-4B",
                    "LARKMEMORY_ENABLE_RERANK=true",
                    "LARKMEMORY_RERANK_BASE_URL=http://127.0.0.1:8002",
                ]
            ),
            encoding="utf-8",
        )

        with patch.dict(os.environ, {"LARKMEMORY_CONFIG_FILE": str(config_path)}, clear=True):
            settings = load_settings()

        self.assertEqual(settings.port, 9010)
        self.assertTrue(settings.enable_embedding)
        self.assertEqual(settings.embedding_provider, "http")
        self.assertEqual(settings.embedding_base_url, "http://127.0.0.1:8001/v1")
        self.assertEqual(settings.embedding_model, "Qwen/Qwen3-Embedding-4B")
        self.assertTrue(settings.enable_rerank)
        self.assertEqual(settings.rerank_base_url, "http://127.0.0.1:8002")

    def test_environment_overrides_env_file_values(self) -> None:
        config_path = self._temp_dir() / "larkmemory.env"
        config_path.write_text("LARKMEMORY_PORT=9010\n", encoding="utf-8")

        with patch.dict(
            os.environ,
            {
                "LARKMEMORY_CONFIG_FILE": str(config_path),
                "LARKMEMORY_PORT": "9020",
            },
            clear=True,
        ):
            settings = load_settings()

        self.assertEqual(settings.port, 9020)

    def test_env_bool_supports_common_values(self) -> None:
        for value in ("1", "true", "yes", "on", "TRUE"):
            with patch.dict(os.environ, {"FLAG": value}, clear=True):
                self.assertTrue(_env_bool("FLAG", False))

        for value in ("0", "false", "no", "off", "FALSE"):
            with patch.dict(os.environ, {"FLAG": value}, clear=True):
                self.assertFalse(_env_bool("FLAG", True))

    def test_env_int_invalid_value_raises_with_name(self) -> None:
        with patch.dict(os.environ, {"PORT": "nope"}, clear=True):
            with self.assertRaisesRegex(ValueError, "PORT"):
                _env_int("PORT", 8765)

    def test_env_float_invalid_value_raises_with_name(self) -> None:
        with patch.dict(os.environ, {"TIMEOUT": "slow"}, clear=True):
            with self.assertRaisesRegex(ValueError, "TIMEOUT"):
                _env_float("TIMEOUT", 60.0)
