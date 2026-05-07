from __future__ import annotations

import unittest
from unittest.mock import patch

from src.sources.feishu.events.models import FeishuCardActionEvent
from src.sources.feishu.proactive.callbacks import FeishuCardActionHandler, parse_card_action
from src.sources.feishu.proactive.cards import (
    build_decision_context_card,
    build_review_reminder_card,
    build_team_memory_strengthened_card,
    build_team_memory_created_card,
)
from src.sources.feishu.proactive.notifier import FeishuNotifier


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

    def test_cards_render_due_at_as_beijing_time(self) -> None:
        card = build_team_memory_created_card(
            {
                "memory_id": "mem-1",
                "content": "客户 A 要求导出 xlsx",
                "due_at": "2026-05-07T22:04:28Z",
                "metadata": {"risk_level": "high"},
            }
        )

        markdown = card["elements"][0]["content"]
        self.assertIn("北京时间 2026-05-08 06:04", markdown)
        self.assertNotIn("2026-05-07T22:04:28Z", markdown)

    def test_build_strengthened_card_contains_next_review(self) -> None:
        card = build_team_memory_strengthened_card(
            {
                "memory_id": "mem-1",
                "content": "星河客户生产数据导出使用 csv 格式。",
                "due_at": "2026-05-07T22:04:28Z",
                "metadata": {"risk_level": "low"},
            }
        )

        self.assertEqual(card["header"]["title"]["content"], "已强化团队记忆")
        markdown = card["elements"][0]["content"]
        self.assertIn("北京时间 2026-05-08 06:04", markdown)
        self.assertIn("下次复习", markdown)

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

    def test_build_decision_context_card_contains_summary_and_actions(self) -> None:
        card = build_decision_context_card(
            {
                "memory_id": "mem-1",
                "topic": "方案选型",
                "decision": "采用方案 B",
                "summary": "当前决策和历史方案 B 讨论有关",
                "bullets": ["之前也优先方案 B", "历史上放弃方案 A"],
                "related_memory_ids": ["mem-2", "mem-3"],
                "suggested_action": "查看历史决策上下文",
            }
        )

        self.assertEqual(card["header"]["title"]["content"], "相关历史决策")
        markdown = card["elements"][0]["content"]
        self.assertIn("方案选型", markdown)
        self.assertIn("之前也优先方案 B", markdown)
        actions = card["elements"][1]["actions"]
        self.assertEqual(actions[0]["value"]["action"], "reviewed")
        self.assertEqual(actions[0]["value"]["memory_id"], "mem-1")

    def test_notifier_send_decision_context_uses_interactive_card(self) -> None:
        notifier = FeishuNotifier(client=object())
        suggestion = {
            "memory_id": "mem-1",
            "topic": "方案选型",
            "decision": "采用方案 B",
            "summary": "当前决策和历史方案 B 讨论有关",
            "bullets": ["之前也优先方案 B"],
            "related_memory_ids": ["mem-2"],
            "suggested_action": "查看历史决策上下文",
        }

        with patch.object(notifier, "send_interactive_card", return_value={"ok": True}) as mocked:
            response = notifier.send_decision_context("oc_1", suggestion)

        self.assertEqual(response, {"ok": True})
        mocked.assert_called_once()
        self.assertEqual(mocked.call_args.args[0], "oc_1")

    def test_card_action_handler_updates_memory_service(self) -> None:
        service = _FakeMemoryService()
        handler = FeishuCardActionHandler(service)  # type: ignore[arg-type]

        response = handler.handle(FeishuCardActionEvent(action="snooze", memory_id="mem-1", snooze_days=1))

        self.assertEqual(service.calls, [("snooze", {"memory_id": "mem-1", "snooze_days": 1})])
        self.assertEqual(response["toast"]["type"], "info")

    def test_card_action_handler_returns_warning_when_update_fails(self) -> None:
        class FailingMemoryService:
            def update_memory(self, action: str, **kwargs: object) -> object:
                raise RuntimeError("boom")

        handler = FeishuCardActionHandler(FailingMemoryService())  # type: ignore[arg-type]

        response = handler.handle(FeishuCardActionEvent(action="promote_to_active", memory_id="mem-1"))

        self.assertEqual(response["toast"]["type"], "warning")
        self.assertIn("操作失败", response["toast"]["content"])

    def test_card_action_handler_rejects_missing_memory_id(self) -> None:
        service = _FakeMemoryService()
        handler = FeishuCardActionHandler(service)  # type: ignore[arg-type]

        response = handler.handle(FeishuCardActionEvent(action="reviewed"))

        self.assertEqual(service.calls, [])
        self.assertEqual(response["toast"]["type"], "warning")
