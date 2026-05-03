from __future__ import annotations

import unittest

from src.core.domain_classifier import DomainClassifier
from src.core.router import DomainRouter, RouteDecision, RouteTarget
from src.schemas import EventContext, NormalizedEvent


class FakeRouteLLM:
    def __init__(self, label: str) -> None:
        self.label = label
        self.calls: list[dict[str, object]] = []

    async def atext(
        self,
        system_prompt: str | None,
        user_prompt: str,
        **kwargs: object,
    ) -> str:
        self.calls.append({
            "system_prompt": system_prompt or "",
            "user_prompt": user_prompt,
            "kwargs": kwargs,
        })
        return self.label


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

    # ---- hard rules ----

    def test_command_finished_routes_to_cli_workflow(self) -> None:
        decision = self.router.route_event(self._event("command_finished"))
        self.assertEqual(decision.primary[0].domain, "cli_workflow")
        self.assertEqual(decision.primary[0].reason, "command event")

    def test_command_failed_routes_to_cli_workflow(self) -> None:
        decision = self.router.route_event(self._event("command_failed", "npm install failed"))
        self.assertEqual(decision.primary[0].domain, "cli_workflow")

    # ---- keyword rules ----

    def test_project_decision_keywords(self) -> None:
        decision = self.router.route_event(
            self._event("chat_message", "决定采用方案 B")
        )
        self.assertEqual(decision.primary[0].domain, "project_decision")

    def test_personal_preference_keywords(self) -> None:
        decision = self.router.route_event(
            self._event("chat_message", "用户偏好默认中文")
        )
        self.assertEqual(decision.primary[0].domain, "personal_preference")

    def test_team_retention_keywords(self) -> None:
        decision = self.router.route_event(
            self._event("chat_message", "提醒截止日期风险")
        )
        self.assertEqual(decision.primary[0].domain, "team_retention")

    def test_cli_workflow_keywords_from_chat(self) -> None:
        decision = self.router.route_event(
            self._event("chat_message", "部署后台服务用 lark project deploy --env staging")
        )
        self.assertEqual(decision.primary[0].domain, "cli_workflow")

    def test_retention_signal_wins_over_decision_keywords(self) -> None:
        event = self._event(
            "chat_message",
            "请团队长期记住：我们决定客户 A 导出使用 xlsx。",
        )
        self.assertEqual(
            self.router.route_event(event).primary[0].domain, "team_retention"
        )

    def test_fallback_not_empty(self) -> None:
        decision = self.router.route_event(self._event("chat_message", "hello"))
        self.assertTrue(decision.primary)

    # ---- LLM routing ----

    def test_route_event_uses_llm_when_available(self) -> None:
        llm = FakeRouteLLM("project_decision")
        classifier = DomainClassifier(llm_client=llm)
        router = DomainRouter(classifier=classifier)

        decision = router.route_event(self._event("chat_message", "我们准备定方案"))

        self.assertEqual(decision.primary[0].domain, "project_decision")
        self.assertEqual(len(llm.calls), 1)
        self.assertEqual(llm.calls[0]["kwargs"]["temperature"], 0)

    # ---- utilities ----

    def test_get_target_domains_dedupes(self) -> None:
        decision = RouteDecision(
            primary=[RouteTarget("project_decision"), RouteTarget("team_retention")],
            secondary=[RouteTarget("project_decision"), RouteTarget("cli_workflow")],
        )
        self.assertEqual(
            DomainRouter.get_target_domains(decision),
            ["project_decision", "team_retention", "cli_workflow"],
        )
