from __future__ import annotations

from typing import Any

from .config import FeishuSettings


def _import_lark() -> Any:
    """Import lark-oapi lazily so unit tests can run without Feishu SDK installed."""
    try:
        import lark_oapi as lark  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("Missing optional dependency: install lark-oapi to use Feishu integration") from exc
    return lark


def build_api_client(settings: FeishuSettings) -> Any:
    """Create a Feishu OpenAPI client for sending messages and cards."""
    settings.require_app_credentials()
    lark = _import_lark()
    return (
        lark.Client.builder()
        .app_id(settings.app_id)
        .app_secret(settings.app_secret)
        .build()
    )


def build_ws_client(settings: FeishuSettings, event_handler: Any) -> Any:
    """Create a Feishu WebSocket client with the provided event dispatcher handler."""
    settings.require_app_credentials()
    lark = _import_lark()
    log_level = getattr(lark.LogLevel, str(settings.log_level).upper(), lark.LogLevel.INFO)
    return lark.ws.Client(
        settings.app_id,
        settings.app_secret,
        event_handler=event_handler,
        log_level=log_level,
    )
