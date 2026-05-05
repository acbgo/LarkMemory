from __future__ import annotations

from typing import Any

from src.core.service import MemoryService

from ..events.models import FeishuCardActionEvent


SUPPORTED_CARD_ACTIONS = {"reviewed", "snooze", "expire", "forget", "acknowledge", "promote_to_active", "dismiss_candidate"}


def parse_card_action(raw_action: dict[str, Any]) -> FeishuCardActionEvent:
    """Parse a Feishu card action value into an internal card action event."""
    value = raw_action.get("value") if "value" in raw_action else raw_action
    if not isinstance(value, dict):
        value = {}
    operator = raw_action.get("operator")
    if not isinstance(operator, dict):
        operator = {}
    return FeishuCardActionEvent(
        action=str(value.get("action") or ""),
        memory_id=value.get("memory_id") if isinstance(value.get("memory_id"), str) else None,
        operator_id=operator.get("open_id") if isinstance(operator.get("open_id"), str) else None,
        chat_id=value.get("chat_id") if isinstance(value.get("chat_id"), str) else None,
        snooze_days=_int_or_none(value.get("snooze_days")),
        raw_payload=dict(raw_action),
    )


class FeishuCardActionHandler:
    """Apply Feishu interactive-card actions to MemoryService update operations."""

    def __init__(self, memory_service: MemoryService) -> None:
        self.memory_service = memory_service

    def handle(self, event: FeishuCardActionEvent) -> dict[str, Any]:
        """Handle a card action and return a Feishu callback toast payload."""
        if event.action not in SUPPORTED_CARD_ACTIONS:
            return _toast("warning", "未知操作")
        if not event.memory_id:
            return _toast("warning", "缺少 memory_id")
        kwargs: dict[str, Any] = {"memory_id": event.memory_id}
        if event.action == "snooze":
            kwargs["snooze_days"] = event.snooze_days or 1
        result = self.memory_service.update_memory(event.action, **kwargs)
        if result.updated or event.action in {"expire", "forget"}:
            return _toast("info", _success_message(event.action))
        return _toast("info", result.message or _success_message(event.action))


def _toast(toast_type: str, content: str) -> dict[str, Any]:
    return {"toast": {"type": toast_type, "content": content}}


def _success_message(action: str) -> str:
    return {
        "reviewed": "已标记复习完成",
        "snooze": "已顺延提醒",
        "expire": "已废弃记忆",
        "forget": "已遗忘记忆",
        "acknowledge": "已确认",
        "promote_to_active": "已创建复习提醒",
        "dismiss_candidate": "已忽略",
    }.get(action, "操作已完成")


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
