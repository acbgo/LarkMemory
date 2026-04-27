from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from src.app.config import _env_bool, _env_float, _env_int, load_settings


class TestConfig(unittest.TestCase):
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

    def test_load_settings_reads_environment_overrides(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LARKMEMORY_PORT": "9000",
                "LARKMEMORY_DEBUG": "true",
                "LARKMEMORY_SQLITE_PATH": ".tmp-tests/app.db",
            },
            clear=True,
        ):
            settings = load_settings()

        self.assertEqual(settings.port, 9000)
        self.assertTrue(settings.debug)
        self.assertEqual(settings.sqlite_path, ".tmp-tests/app.db")

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

