from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.utils.time import days_between

from .models import TeamRetentionMemory


@dataclass(slots=True)
class TeamRetentionRankWeights:
    relevance: float = 0.4
    risk: float = 0.25
    scope: float = 0.15
    confidence: float = 0.1
    review_due: float = 0.1

    def normalized(self) -> TeamRetentionRankWeights:
        total = self.relevance + self.risk + self.scope + self.confidence + self.review_due
        if total <= 0:
            return TeamRetentionRankWeights()
        return TeamRetentionRankWeights(
            relevance=self.relevance / total,
            risk=self.risk / total,
            scope=self.scope / total,
            confidence=self.confidence / total,
            review_due=self.review_due / total,
        )


class TeamRetentionRanker:
    def __init__(self, weights: TeamRetentionRankWeights | None = None) -> None:
        self.weights = (weights or TeamRetentionRankWeights()).normalized()

    def rank(self, results: list[Any], query: Any, *, limit: int | None = None) -> list[Any]:
        for result in results:
            result.score = self.score_result(result, query)
        ranked = sorted(
            results,
            key=lambda result: (
                result.score,
                result.memory.risk_level == "high",
                result.memory.updated_at or "",
            ),
            reverse=True,
        )
        return ranked[:limit] if limit is not None else ranked

    def score_result(self, result: Any, query: Any) -> float:
        memory: TeamRetentionMemory = result.memory
        score = (
            self._clamp(result.score) * self.weights.relevance
            + self.risk_score(memory) * self.weights.risk
            + self.scope_score(memory, query) * self.weights.scope
            + self._clamp(memory.confidence) * self.weights.confidence
            + self.review_due_score(memory, getattr(query, "timestamp", None)) * self.weights.review_due
        )
        return self._clamp(score)

    def risk_score(self, memory: TeamRetentionMemory) -> float:
        return {"high": 1.0, "medium": 0.65, "low": 0.35}.get(memory.risk_level, 0.5)

    def scope_score(self, memory: TeamRetentionMemory, query: Any) -> float:
        score = 0.0
        if getattr(query, "team_id", None) and query.team_id == memory.team_id:
            score += 0.5
        if getattr(query, "project_id", None) and query.project_id == memory.project_id:
            score += 0.35
        if getattr(query, "workspace_id", None) and query.workspace_id == memory.workspace_id:
            score += 0.15
        return self._clamp(score)

    def review_due_score(self, memory: TeamRetentionMemory, now_iso: str | None = None) -> float:
        if not memory.next_review_at:
            return 0.0
        try:
            age = days_between(memory.next_review_at, now_iso) if now_iso else days_between(memory.next_review_at)
        except ValueError:
            return 0.0
        return 1.0 if age >= 0 else 0.0

    def _clamp(self, value: float) -> float:
        return max(0.0, min(1.0, float(value)))
