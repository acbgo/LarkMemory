from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class FeishuSettings:
    """Feishu app credentials and listener/notifier runtime settings."""

    app_id: str | None = None
    app_secret: str | None = None
    encrypt_key: str | None = None
    verification_token: str | None = None
    default_chat_id: str | None = None
    enable_ws: bool = False
    request_timeout: float = 10.0
    log_level: str = "INFO"

    def require_app_credentials(self) -> None:
        """Validate app-level credentials before creating Feishu SDK clients."""
        if not self.app_id or not self.app_secret:
            raise ValueError("LARKMEMORY_FEISHU_APP_ID and LARKMEMORY_FEISHU_APP_SECRET are required")


def _load_env_file(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    config_path = Path(path)
    if not config_path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _env_str(
    name: str, default: str | None = None, file_values: Mapping[str, str] | None = None
) -> str | None:
    value = os.getenv(name)
    if value is None and file_values is not None:
        value = file_values.get(name)
    if value is None:
        return default
    return value or None


def _env_bool(
    name: str, default: bool = False, file_values: Mapping[str, str] | None = None
) -> bool:
    value = os.getenv(name)
    if value is None and file_values is not None:
        value = file_values.get(name)
    if value is None or value == "":
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean for {name}: {value!r}")


def _env_float(
    name: str, default: float, file_values: Mapping[str, str] | None = None
) -> float:
    value = os.getenv(name)
    if value is None and file_values is not None:
        value = file_values.get(name)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"Invalid float for {name}: {value!r}") from exc


def load_feishu_settings() -> FeishuSettings:
    """Load Feishu source adapter settings from LARKMEMORY_FEISHU_* env vars and config file."""
    file_values = _load_env_file(os.getenv("LARKMEMORY_CONFIG_FILE", "larkmemory.env"))
    return FeishuSettings(
        app_id=_env_str("LARKMEMORY_FEISHU_APP_ID", file_values=file_values),
        app_secret=_env_str("LARKMEMORY_FEISHU_APP_SECRET", file_values=file_values),
        encrypt_key=_env_str("LARKMEMORY_FEISHU_ENCRYPT_KEY", file_values=file_values),
        verification_token=_env_str("LARKMEMORY_FEISHU_VERIFICATION_TOKEN", file_values=file_values),
        default_chat_id=_env_str("LARKMEMORY_FEISHU_DEFAULT_CHAT_ID", file_values=file_values),
        enable_ws=_env_bool("LARKMEMORY_FEISHU_ENABLE_WS", False, file_values),
        request_timeout=_env_float("LARKMEMORY_FEISHU_REQUEST_TIMEOUT", 10.0, file_values),
        log_level=_env_str("LARKMEMORY_FEISHU_LOG_LEVEL", "INFO", file_values) or "INFO",
    )
