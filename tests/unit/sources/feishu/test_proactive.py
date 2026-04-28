from __future__ import annotations

import unittest

from src.sources.feishu.events.models import FeishuCardActionEvent
from src.sources.feishu.proactive.callbacks import FeishuCardActionHandler, parse_card_action
from src.sources.feishu.proactive.cards import build_review_reminder_card


class _FakeMemoryService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def update_memory(self, action: str, **kwargs: object) -> object:
        self.calls.append((action, kwargs))

        class Result:
            updated = True
            message = "ok"

        return Result()


class TestFeishuProactive(unittest.TestCase):
    def test_build_review_reminder_card_contains_actions(self) -> None:
        card = build_review_reminder_card(
            {
                "memory_id": "mem-1",
                "content": "客户 A 要求导出 xlsx",
                "due_at": "2026-04-28T00:00:00Z",
                "metadata": {"risk_level": "high"},
            }
        )

        self.assertEqual(card["header"]["template"], "red")
        actions = card["elements"][1]["actions"]
        self.assertEqual(actions[0]["value"]["action"], "reviewed")
        self.assertEqual(actions[1]["value"]["action"], "snooze")
        self.assertEqual(actions[2]["value"]["action"], "expire")

    def test_parse_card_action_reads_value(self) -> None:
        event = parse_card_action(
            {
                "value": {"action": "snooze", "memory_id": "mem-1", "snooze_days": "2"},
                "operator": {"open_id": "ou-1"},
            }
        )

        self.assertEqual(event.action, "snooze")
        self.assertEqual(event.memory_id, "mem-1")
        self.assertEqual(event.snooze_days, 2)
        self.assertEqual(event.operator_id, "ou-1")

    def test_card_action_handler_updates_memory_service(self) -> None:
        service = _FakeMemoryService()
        handler = FeishuCardActionHandler(service)  # type: ignore[arg-type]

        response = handler.handle(FeishuCardActionEvent(action="snooze", memory_id="mem-1", snooze_days=1))

        self.assertEqual(service.calls, [("snooze", {"memory_id": "mem-1", "snooze_days": 1})])
        self.assertEqual(response["toast"]["type"], "info")

    def test_card_action_handler_rejects_missing_memory_id(self) -> None:
        service = _FakeMemoryService()
        handler = FeishuCardActionHandler(service)  # type: ignore[arg-type]

        response = handler.handle(FeishuCardActionEvent(action="reviewed"))

        self.assertEqual(service.calls, [])
        self.assertEqual(response["toast"]["type"], "warning")
