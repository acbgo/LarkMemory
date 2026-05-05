from __future__ import annotations

import os
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from src.sources.feishu.client.config import (
    _env_bool,
    _env_float,
    _env_str,
    load_feishu_settings,
)


class TestFeishuConfig(unittest.TestCase):
    def _temp_dir(self) -> Path:
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        temp_dir = root / f"feishu-config-{uuid.uuid4().hex}"
        temp_dir.mkdir()
        self.addCleanup(shutil.rmtree, temp_dir, True)
        return temp_dir

    def test_load_settings_defaults(self) -> None:
        with patch.dict(
            os.environ,
            {"LARKMEMORY_CONFIG_FILE": str(self._temp_dir() / "missing.env")},
            clear=True,
        ):
            settings = load_feishu_settings()

        self.assertIsNone(settings.app_id)
        self.assertIsNone(settings.app_secret)
        self.assertIsNone(settings.encrypt_key)
        self.assertIsNone(settings.verification_token)
        self.assertIsNone(settings.default_chat_id)
        self.assertFalse(settings.enable_ws)
        self.assertEqual(settings.request_timeout, 10.0)
        self.assertEqual(settings.log_level, "INFO")

    def test_load_settings_reads_environment_overrides(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LARKMEMORY_FEISHU_APP_ID": "env_app_id",
                "LARKMEMORY_FEISHU_APP_SECRET": "env_secret",
                "LARKMEMORY_FEISHU_DEFAULT_CHAT_ID": "env_chat_id",
                "LARKMEMORY_FEISHU_ENABLE_WS": "true",
                "LARKMEMORY_FEISHU_REQUEST_TIMEOUT": "5.0",
                "LARKMEMORY_FEISHU_LOG_LEVEL": "DEBUG",
            },
            clear=True,
        ):
            settings = load_feishu_settings()

        self.assertEqual(settings.app_id, "env_app_id")
        self.assertEqual(settings.app_secret, "env_secret")
        self.assertEqual(settings.default_chat_id, "env_chat_id")
        self.assertTrue(settings.enable_ws)
        self.assertEqual(settings.request_timeout, 5.0)
        self.assertEqual(settings.log_level, "DEBUG")

    def test_load_settings_reads_env_file(self) -> None:
        config_path = self._temp_dir() / "larkmemory.env"
        config_path.write_text(
            "\n".join(
                [
                    "# feishu credentials",
                    "LARKMEMORY_FEISHU_APP_ID=file_app_id",
                    "LARKMEMORY_FEISHU_APP_SECRET=file_secret",
                    "LARKMEMORY_FEISHU_DEFAULT_CHAT_ID=file_chat_id",
                ]
            ),
            encoding="utf-8",
        )

        with patch.dict(os.environ, {"LARKMEMORY_CONFIG_FILE": str(config_path)}, clear=True):
            settings = load_feishu_settings()

        self.assertEqual(settings.app_id, "file_app_id")
        self.assertEqual(settings.app_secret, "file_secret")
        self.assertEqual(settings.default_chat_id, "file_chat_id")

    def test_environment_overrides_env_file(self) -> None:
        config_path = self._temp_dir() / "larkmemory.env"
        config_path.write_text(
            "LARKMEMORY_FEISHU_APP_ID=file_app_id\n",
            encoding="utf-8",
        )

        with patch.dict(
            os.environ,
            {
                "LARKMEMORY_CONFIG_FILE": str(config_path),
                "LARKMEMORY_FEISHU_APP_ID": "env_app_id",
            },
            clear=True,
        ):
            settings = load_feishu_settings()

        self.assertEqual(settings.app_id, "env_app_id")

    def test_load_settings_default_config_file(self) -> None:
        """When LARKMEMORY_CONFIG_FILE is not set, it falls back to larkmemory.env."""
        config_path = Path("larkmemory.env")
        original_content = None
        if config_path.exists():
            original_content = config_path.read_text(encoding="utf-8")

        try:
            config_path.write_text(
                "LARKMEMORY_FEISHU_APP_ID=default_file_app_id\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                settings = load_feishu_settings()

            self.assertEqual(settings.app_id, "default_file_app_id")
        finally:
            if original_content is not None:
                config_path.write_text(original_content, encoding="utf-8")
            elif config_path.exists() and original_content is None:
                config_path.unlink()

    def test_require_app_credentials_raises_when_missing(self) -> None:
        from src.sources.feishu.client.config import FeishuSettings

        with self.assertRaisesRegex(ValueError, "LARKMEMORY_FEISHU_APP_ID"):
            FeishuSettings().require_app_credentials()

        with self.assertRaisesRegex(ValueError, "LARKMEMORY_FEISHU_APP_ID"):
            FeishuSettings(app_id="id").require_app_credentials()

        FeishuSettings(app_id="id", app_secret="secret").require_app_credentials()

    def test_env_bool_supports_common_values(self) -> None:
        for value in ("1", "true", "yes", "on", "TRUE"):
            with patch.dict(os.environ, {"FLAG": value}, clear=True):
                self.assertTrue(_env_bool("FLAG", False))

        for value in ("0", "false", "no", "off", "FALSE"):
            with patch.dict(os.environ, {"FLAG": value}, clear=True):
                self.assertFalse(_env_bool("FLAG", True))

    def test_env_str_reads_from_file_values(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            value = _env_str("KEY", file_values={"KEY": "from_file"})
        self.assertEqual(value, "from_file")

    def test_env_str_env_beats_file(self) -> None:
        with patch.dict(os.environ, {"KEY": "from_env"}, clear=True):
            value = _env_str("KEY", file_values={"KEY": "from_file"})
        self.assertEqual(value, "from_env")

    def test_env_float_invalid_value_raises(self) -> None:
        with patch.dict(os.environ, {"TIMEOUT": "slow"}, clear=True):
            with self.assertRaisesRegex(ValueError, "TIMEOUT"):
                _env_float("TIMEOUT", 60.0)
