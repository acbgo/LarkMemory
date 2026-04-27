from __future__ import annotations

import unittest

from src.core.router import DomainRouter, RouteDecision, RouteTarget
from src.retrieval import IntentResult, MemoryDomain, RetrievalQuery
from src.schemas import EventContext, NormalizedEvent


class TestRouter(unittest.TestCase):
    def setUp(self) -> None:
        self.router = DomainRouter()

    def _event(self, event_type: str, text: str = "") -> NormalizedEvent:
        return NormalizedEvent(
            event_id="event-1",
            event_type=event_type,  # type: ignore[arg-type]
            source_type="feishu_chat",
            occurred_at="2026-04-27T00:00:00Z",
            context=EventContext(),
            content_text=text,
        )

    def test_event_routes(self) -> None:
        self.assertEqual(
            self.router.route_event(self._event("command_finished")).primary[0].domain,
            "cli_workflow",
        )
        self.assertEqual(
            self.router.route_event(self._event("chat_message", "决定采用方案 B")).primary[0].domain,
            "project_decision",
        )
        self.assertEqual(
            self.router.route_event(self._event("chat_message", "用户偏好默认中文")).primary[0].domain,
            "personal_preference",
        )
        self.assertEqual(
            self.router.route_event(self._event("chat_message", "提醒截止日期风险")).primary[0].domain,
            "team_retention",
        )

    def test_retention_signal_wins_over_decision_keywords(self) -> None:
        event = self._event(
            "chat_message",
            "请团队长期记住：我们决定客户 A 导出使用 xlsx。",
        )

        self.assertEqual(self.router.route_event(event).primary[0].domain, "team_retention")

    def test_fallback_not_empty(self) -> None:
        decision = self.router.route_event(self._event("chat_message", "hello"))

        self.assertTrue(decision.fallback_used)
        self.assertTrue(decision.primary)

    def test_route_query_uses_intent_first(self) -> None:
        decision = self.router.route_query(
            RetrievalQuery("anything"),
            IntentResult(primary_domains=[MemoryDomain.PROJECT_DECISION]),
        )

        self.assertEqual(decision.primary[0].domain, "project_decision")

    def test_get_target_domains_dedupes(self) -> None:
        decision = RouteDecision(
            primary=[RouteTarget("project_decision"), RouteTarget("team_retention")],
            secondary=[RouteTarget("project_decision"), RouteTarget("cli_workflow")],
        )

        self.assertEqual(
            DomainRouter.get_target_domains(decision),
            ["project_decision", "team_retention", "cli_workflow"],
        )

