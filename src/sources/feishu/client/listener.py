from __future__ import annotations

import json
import logging
from typing import Any

from src.app.dependencies import get_memory_service
from src.sources.feishu.events.dispatcher import FeishuEventDispatcher
from src.sources.feishu.events.models import FeishuMessageEvent
from src.sources.feishu.events.normalizer import extract_text_from_message_content
from src.sources.feishu.proactive.callbacks import FeishuCardActionHandler, parse_card_action

from .config import load_feishu_settings
from .sdk import build_ws_client, _import_lark


logger = logging.getLogger(__name__)


def build_event_handler(memory_service: Any | None = None, settings: Any | None = None) -> Any:
    """Build lark-oapi event handler for Feishu messages and card actions."""
    lark = _import_lark()
    service = memory_service or get_memory_service()
    dispatcher = FeishuEventDispatcher(service)
    card_handler = FeishuCardActionHandler(service)

    def on_message(data: Any) -> None:
        message_event = _message_event_from_lark(data)
        if message_event is None:
            logger.info("function=src.sources.feishu.client.listener.on_message action=skip_empty")
            return
        dispatcher.dispatch_message(message_event)

    def on_card_action(data: Any) -> Any:
        raw_action = _card_action_from_lark(data)
        response_payload = card_handler.handle(parse_card_action(raw_action))
        try:
            from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTriggerResponse  # type: ignore[import-not-found]
        except ImportError:
            return response_payload
        return P2CardActionTriggerResponse(response_payload)

    return (
        lark.EventDispatcherHandler.builder(
            getattr(settings, "verification_token", "") if settings is not None else "",
            getattr(settings, "encrypt_key", "") if settings is not None else "",
        )
        .register_p2_im_message_receive_v1(on_message)
        .register_p2_card_action_trigger(on_card_action)
        .build()
    )


def main() -> None:
    """Start the Feishu WebSocket listener as a standalone source worker."""
    settings = load_feishu_settings()
    if not settings.enable_ws:
        raise RuntimeError("Feishu WebSocket listener is disabled; set LARKMEMORY_FEISHU_ENABLE_WS=true")
    client = build_ws_client(settings, build_event_handler(settings=settings))
    client.start()


def _message_event_from_lark(data: Any) -> FeishuMessageEvent | None:
    event = getattr(data, "event", None)
    message = getattr(event, "message", None)
    sender = getattr(event, "sender", None)
    sender_id = getattr(sender, "sender_id", None)
    message_id = getattr(message, "message_id", None)
    chat_id = getattr(message, "chat_id", None)
    message_type = getattr(message, "message_type", "text")
    if not message_id or not chat_id:
        return None
    content_text = extract_text_from_message_content(message_type, getattr(message, "content", None))
    return FeishuMessageEvent(
        message_id=str(message_id),
        chat_id=str(chat_id),
        chat_type=str(getattr(message, "chat_type", "") or ""),
        sender_id=getattr(sender_id, "open_id", None),
        message_type=str(message_type),
        content_text=content_text,
        create_time=str(getattr(message, "create_time", "") or "") or None,
        raw_payload=_safe_payload(data),
    )


def _card_action_from_lark(data: Any) -> dict[str, Any]:
    event = getattr(data, "event", None)
    action = getattr(event, "action", None)
    operator = getattr(event, "operator", None)
    return {
        "value": getattr(action, "value", {}) or {},
        "operator": {"open_id": getattr(operator, "open_id", None)},
        "raw": _safe_payload(data),
    }


def _safe_payload(data: Any) -> dict[str, Any]:
    if hasattr(data, "raw"):
        raw = getattr(data, "raw")
        if isinstance(raw, dict):
            return raw
    try:
        return json.loads(json.dumps(data, default=lambda item: getattr(item, "__dict__", str(item))))
    except Exception:
        return {}


if __name__ == "__main__":
    main()
