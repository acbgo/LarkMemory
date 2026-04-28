from __future__ import annotations

import os
from dataclasses import dataclass


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


def _env_str(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    return value or None


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean for {name}: {value!r}")


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"Invalid float for {name}: {value!r}") from exc


def load_feishu_settings() -> FeishuSettings:
    """Load Feishu source adapter settings from LARKMEMORY_FEISHU_* environment variables."""
    return FeishuSettings(
        app_id=_env_str("LARKMEMORY_FEISHU_APP_ID"),
        app_secret=_env_str("LARKMEMORY_FEISHU_APP_SECRET"),
        encrypt_key=_env_str("LARKMEMORY_FEISHU_ENCRYPT_KEY"),
        verification_token=_env_str("LARKMEMORY_FEISHU_VERIFICATION_TOKEN"),
        default_chat_id=_env_str("LARKMEMORY_FEISHU_DEFAULT_CHAT_ID"),
        enable_ws=_env_bool("LARKMEMORY_FEISHU_ENABLE_WS", False),
        request_timeout=_env_float("LARKMEMORY_FEISHU_REQUEST_TIMEOUT", 10.0),
        log_level=_env_str("LARKMEMORY_FEISHU_LOG_LEVEL", "INFO") or "INFO",
    )
