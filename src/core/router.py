from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from src.retrieval import IntentResult, RetrievalQuery
from src.schemas import NormalizedEvent
from src.utils.text import contains_any


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RouteTarget:
    domain: str
    priority: float = 1.0
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RouteDecision:
    primary: list[RouteTarget] = field(default_factory=list)
    secondary: list[RouteTarget] = field(default_factory=list)
    fallback_used: bool = False
    reason: str = ""


class DomainRouter:
    def __init__(self, default_domain: str = "team_retention") -> None:
        self.default_domain = default_domain

    def route_event(self, event: NormalizedEvent) -> RouteDecision:
        text = self._event_text(event)
        if event.event_type in {"command_finished", "command_failed"}:
<<<<<<< HEAD
            return self._single("cli_workflow", "command event")
        # Team retention must win over project_decision when explicit long-term
        # retention signals appear in the same message.
        if self._matches_team_retention(text):
            return self._single("team_retention", "retention keywords")
=======
            decision = self._single("cli_workflow", "command event")
            self.log_event_decision(event, decision)
            return decision
>>>>>>> b99add032b7660e17b81a51e14b6295e37691890
        if self._matches_project_decision(text):
            decision = self._single("project_decision", "decision keywords")
            self.log_event_decision(event, decision)
            return decision
        if contains_any(text, ["偏好", "习惯", "默认", "喜欢", "prefer"]):
            return self._single("personal_preference", "preference keywords")
<<<<<<< HEAD
        return self._fallback()
=======
        if contains_any(text, [
            "提醒", "截止", "合规", "风险", "复习", "保留",
            "长期记住", "团队记住", "不要忘", "请记录", "客户要求", "客户偏好",
            "密钥", "竞品", "遗忘", "deadline", "risk", "remember", "retention",
        ]):
            return self._single("team_retention", "retention keywords")
        decision = self._fallback()
        self.log_event_decision(event, decision)
        return decision
>>>>>>> b99add032b7660e17b81a51e14b6295e37691890

    def route_query(
        self,
        query: RetrievalQuery,
        intent: IntentResult | None = None,
    ) -> RouteDecision:
        if intent is not None:
            decision = RouteDecision(
                primary=[
                    RouteTarget(domain=domain.value, priority=1.0, reason="intent primary")
                    for domain in intent.primary_domains
                ],
                secondary=[
                    RouteTarget(domain=domain.value, priority=0.5, reason="intent secondary")
                    for domain in intent.secondary_domains
                ],
                reason="intent result",
            )
            self.log_query_decision(query, decision)
            return decision
        text = query.query_text
        if contains_any(text, ["deploy", "build", "command", "shell", "npm", "pytest", "命令", "构建", "部署"]):
            return self._single("cli_workflow", "query command keywords")
        if self._matches_team_retention(text):
            return self._single("team_retention", "query retention keywords")
        if self._matches_project_decision(text):
            return self._single("project_decision", "query decision keywords")
        if contains_any(text, ["偏好", "习惯", "默认", "prefer", "usually"]):
            return self._single("personal_preference", "query preference keywords")
        return self._fallback()

    @staticmethod
    def get_target_domains(decision: RouteDecision) -> list[str]:
        domains: list[str] = []
        seen: set[str] = set()
        for target in [*decision.primary, *decision.secondary]:
            if target.domain in seen:
                continue
            seen.add(target.domain)
            domains.append(target.domain)
        return domains

    @staticmethod
    def log_event_decision(event: NormalizedEvent, decision: RouteDecision) -> None:
        logger.info(
            "function=src.core.router.DomainRouter.route_event action=done event_id=%s primary_domains=%s secondary_domains=%s fallback_used=%s reason=%s",
            event.event_id,
            [target.domain for target in decision.primary],
            [target.domain for target in decision.secondary],
            decision.fallback_used,
            decision.reason,
        )

    @staticmethod
    def log_query_decision(query: RetrievalQuery, decision: RouteDecision) -> None:
        del query
        logger.info(
            "function=src.core.router.DomainRouter.route_query action=done primary_domains=%s secondary_domains=%s fallback_used=%s reason=%s",
            [target.domain for target in decision.primary],
            [target.domain for target in decision.secondary],
            decision.fallback_used,
            decision.reason,
        )

    def _fallback(self) -> RouteDecision:
        return RouteDecision(
            primary=[RouteTarget(domain=self.default_domain, reason="fallback default")],
            secondary=[RouteTarget(domain="project_decision", priority=0.5, reason="fallback secondary")],
            fallback_used=True,
            reason="no explicit route matched",
        )

    @staticmethod
    def _single(domain: str, reason: str) -> RouteDecision:
        return RouteDecision(primary=[RouteTarget(domain=domain, reason=reason)], reason=reason)

    @staticmethod
    def _event_text(event: NormalizedEvent) -> str:
        return " ".join(
            part
            for part in [
                event.title or "",
                event.content_text or "",
                str(event.payload or ""),
                str(event.raw_payload or ""),
            ]
            if part
        )

    @staticmethod
    def _matches_project_decision(text: str) -> bool:
        if "截止日期" in text and "确认" not in text:
            return False
        return contains_any(
            text,
            [
                "决定",
                "确认",
                "采用",
                "选择",
                "结论",
                "方案",
                "选型",
                "架构",
                "截止日期",
                "why",
                "decision",
                "rationale",
                "choose",
                "confirmed",
                "替代",
            ],
        )

    @staticmethod
    def _matches_team_retention(text: str) -> bool:
        return contains_any(
            text,
            [
                "提醒",
                "合规",
                "风险",
                "复习",
                "保留",
                "长期记住",
                "团队记住",
                "不要忘",
                "请记录",
                "客户要求",
                "客户偏好",
                "密钥",
                "竞品",
                "遗忘",
                "risk",
                "remember",
                "retention",
                "review",
            ],
        )
