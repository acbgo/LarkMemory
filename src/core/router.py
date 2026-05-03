from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from src.retrieval import IntentResult
from src.schemas import NormalizedEvent

from .domain_classifier import DomainClassifier

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

    def __init__(
        self,
        classifier: DomainClassifier | None = None,
        llm_client: Any | None = None,
    ) -> None:
        self.classifier = classifier or DomainClassifier(llm_client=llm_client)

    def route_event(self, event: NormalizedEvent) -> RouteDecision:
        text = self._event_text(event)
        result = self.classifier.classify_sync(
            text,
            event_type=event.event_type,
        )
        is_fallback = (
            result.method == "keyword_rule"
            and result.confidence <= 0.3
        )
        decision = RouteDecision(
            primary=[
                RouteTarget(domain=d, priority=1.0, reason=result.reason)
                for d in result.primary
            ],
            secondary=[
                RouteTarget(domain=d, priority=0.5, reason="secondary affinity")
                for d in result.secondary
            ],
            fallback_used=is_fallback,
            reason=result.reason,
        )
        return self._log_decision(event, decision)

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

    def _log_decision(self, event: NormalizedEvent, decision: RouteDecision) -> RouteDecision:
        primary = decision.primary[0].domain if decision.primary else None
        logger.info(
            "event_id=%s primary_domain=%s fallback_used=%s reason=%s",
            event.event_id,
            primary,
            decision.fallback_used,
            decision.reason,
        )
        return decision
