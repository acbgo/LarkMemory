from __future__ import annotations

import logging
import asyncio
from dataclasses import asdict, dataclass, field
from typing import Any

from src.retrieval import IntentResult, RetrievalQuery
from src.schemas import NormalizedEvent
from src.utils.text import contains_any


logger = logging.getLogger(__name__)


_ROUTE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "domain": {
            "type": "string",
            "enum": [
                "project_decision",
                "team_retention",
                "personal_preference",
                "cli_workflow",
            ],
        },
    },
    "required": ["domain"],
}

_ROUTE_SYSTEM_PROMPT = """Return JSON only: {"domain": "..."}.
Choose exactly one domain:
- project_decision: decisions, choices, rationales, architecture or technical selection.
- team_retention: facts a team must remember, risks, compliance, deadlines, customer requirements.
- personal_preference: user habits, preferences, defaults.
- cli_workflow: shell commands, build, deploy, troubleshooting workflows."""


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
    def __init__(self, default_domain: str = "team_retention", llm_client: Any | None = None) -> None:
        """Route events and queries to memory domains, optionally using an LLM for event routing."""
        self.default_domain = default_domain
        self.llm_client = llm_client

    def route_event(self, event: NormalizedEvent) -> RouteDecision:
        if self.llm_client is not None:
            decision = self._route_event_with_llm(event)
            if decision is not None:
                return self._log_event_decision(event, decision)
        text = self._event_text(event)
        if event.event_type in {"command_finished", "command_failed"}:
            return self._log_event_decision(event, self._single("cli_workflow", "command event"))
        if self._matches_team_retention(text):
            return self._log_event_decision(event, self._single("team_retention", "retention keywords"))
        if self._matches_project_decision(text):
            return self._log_event_decision(event, self._single("project_decision", "decision keywords"))
        if contains_any(text, ["偏好", "习惯", "默认", "喜欢", "prefer"]):
            return self._log_event_decision(event, self._single("personal_preference", "preference keywords"))
        return self._log_event_decision(event, self._fallback())

    def route_query(
        self,
        query: RetrievalQuery,
        intent: IntentResult | None = None,
    ) -> RouteDecision:
        if intent is not None:
            return RouteDecision(
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

    def _route_event_with_llm(self, event: NormalizedEvent) -> RouteDecision | None:
        """Ask the LLM to choose the primary domain; invalid or low-confidence output falls back to rules."""
        try:
            raw = _run_async(
                self.llm_client.ajson(  # type: ignore[union-attr]
                    _ROUTE_SYSTEM_PROMPT,
                    f"Route this event:\n{event.content_text}",
                    schema=_ROUTE_SCHEMA,
                    temperature=0,
                    max_tokens=1024,
                )
            )
        except Exception:
            logger.exception(
                "action=llm_route_failed event_id=%s",
                event.event_id,
            )
            return None

        primary = str(raw.get("domain") or "")
        logger.info(
            "action=llm_route event_id=%s primary_domain=%s",
            event.event_id,
            primary,
        )
        if primary not in {"project_decision", "team_retention", "personal_preference", "cli_workflow"}:
            return None
        return RouteDecision(
            primary=[RouteTarget(domain=primary, priority=1.0, reason="llm route")],
            reason="llm route",
        )

    def _log_event_decision(self, event: NormalizedEvent, decision: RouteDecision) -> RouteDecision:
        primary = decision.primary[0].domain if decision.primary else None
        logger.info(
            "event_id=%s primary_domain=%s fallback_used=%s reason=%s",
            event.event_id,
            primary,
            decision.fallback_used,
            decision.reason,
        )
        return decision


def _run_async(awaitable: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    raise RuntimeError("DomainRouter sync API cannot run inside an active event loop")
