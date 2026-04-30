from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.utils.time import days_between

from .models import ProjectDecision


@dataclass(slots=True)
class DecisionRankWeights:
    relevance: float = 0.45
    freshness: float = 0.2
    confidence: float = 0.15
    importance: float = 0.15
    authority: float = 0.05

    def normalized(self) -> DecisionRankWeights:
        total = self.relevance + self.freshness + self.confidence + self.importance + self.authority
        if total <= 0:
            return DecisionRankWeights()
        return DecisionRankWeights(
            relevance=self.relevance / total,
            freshness=self.freshness / total,
            confidence=self.confidence / total,
            importance=self.importance / total,
            authority=self.authority / total,
        )


class ProjectDecisionRanker:
    """Ranks project decision search results by relevance, freshness, and trust."""

    def __init__(self, weights: DecisionRankWeights | None = None) -> None:
        self.weights = (weights or DecisionRankWeights()).normalized()

    def rank(
        self,
        results: list[Any],
        query: Any,
        *,
        limit: int | None = None,
    ) -> list[Any]:
        for result in results:
            result.score = self.score_result(result, query)
        ranked = sorted(
            results,
            key=lambda result: (
                result.score,
                result.decision.decided_at or "",
                result.decision.decision_id,
            ),
            reverse=True,
        )
        return ranked[:limit] if limit is not None else ranked

    def score_result(self, result: Any, query: Any) -> float:
        decision = result.decision
        score = (
            self.relevance_score(result, query) * self.weights.relevance
            + self.freshness_score(decision, now_iso=getattr(query, "timestamp", None)) * self.weights.freshness
            + self._clamp_score(decision.confidence) * self.weights.confidence
            + self._clamp_score(decision.importance) * self.weights.importance
            + self.authority_score(decision) * self.weights.authority
        )
        if decision.status == "superseded":
            score *= 0.2
        return self._clamp_score(score)

    def relevance_score(self, result: Any, query: Any) -> float:
        score = min(len(getattr(result, "matched_fields", [])) * 0.16, 0.5)
        query_topic = (getattr(query, "topic", None) or "").lower()
        if query_topic and query_topic == result.decision.topic.lower():
            score += 0.35
        elif query_topic and query_topic in result.decision.topic.lower():
            score += 0.2
        if getattr(query, "project_id", None) and query.project_id == result.decision.project_id:
            score += 0.15
        if getattr(query, "stage", None) and query.stage == result.decision.stage:
            score += 0.1
        text = (getattr(query, "query_text", "") or "").lower()
        if any(keyword in text for keyword in ("之前决定", "历史决策", "为什么选", "方案")):
            score += 0.15
        return self._clamp_score(max(score, getattr(result, "score", 0.0)))

    def freshness_score(self, decision: ProjectDecision, *, now_iso: str | None = None) -> float:
        if decision.status == "superseded":
            return 0.0
        reference = decision.decided_at
        if not reference:
            return 0.6
        try:
            age = max(days_between(reference, now_iso), 0.0) if now_iso else max(days_between(reference), 0.0)
        except ValueError:
            return 0.5
        if age <= 30:
            return 1.0
        if age <= 90:
            return 0.75
        if age <= 180:
            return 0.45
        return 0.2

    def authority_score(self, decision: ProjectDecision) -> float:
        source = decision.source_type
        score = 0.45
        if source in {"meeting", "feishu_doc", "task_system"}:
            score += 0.3
        if source == "feishu_chat":
            score += 0.1
        if decision.confidence < 0.45:
            score = min(score, 0.5)
        return self._clamp_score(score)

    def _clamp_score(self, value: float) -> float:
        return max(0.0, min(1.0, float(value)))
