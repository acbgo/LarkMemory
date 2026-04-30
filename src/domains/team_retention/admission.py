from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .llm_extractor import TeamRetentionLLMExtraction


TeamRetentionAdmissionStatus = Literal["reject", "candidate", "active"]


@dataclass(slots=True)
class TeamRetentionAdmissionDecision:
    status: TeamRetentionAdmissionStatus
    score: float
    confidence: float
    importance: float
    reason: str


class TeamRetentionAdmissionDecider:
    """Apply deterministic thresholds to LLM score breakdowns."""

    WEIGHTS = {
        "explicit_intent": 0.18,
        "future_dependency": 0.18,
        "cross_member_dependency": 0.16,
        "risk_or_cost": 0.16,
        "source_authority": 0.10,
        "stability": 0.10,
        "actionability": 0.08,
        "uncertainty_penalty": -0.08,
        "sensitivity_penalty": -0.08,
        "triviality_penalty": -0.04,
    }

    def decide(
        self,
        extraction: TeamRetentionLLMExtraction,
        *,
        sensitive_unmasked: bool = False,
    ) -> TeamRetentionAdmissionDecision:
        """Return final reject/candidate/active status from extraction scores."""
        score = self.score(extraction.score_breakdown)
        confidence = _clamp(extraction.confidence)
        importance = _clamp(extraction.importance or score)
        if not extraction.is_team_retention_memory or not extraction.fact_value:
            return TeamRetentionAdmissionDecision("reject", score, confidence, importance, "not_team_retention")
        if score < 0.45 and extraction.decision != "candidate":
            return TeamRetentionAdmissionDecision("reject", score, confidence, importance, "score_below_candidate")
        if (
            extraction.decision == "active"
            and score >= 0.75
            and confidence >= 0.70
            and not extraction.needs_confirmation
            and not sensitive_unmasked
        ):
            return TeamRetentionAdmissionDecision("active", score, confidence, importance, "active_threshold_met")
        return TeamRetentionAdmissionDecision("candidate", score, confidence, importance, "candidate_or_downgraded")

    def score(self, breakdown: dict[str, float]) -> float:
        """Compute the backend-owned team_retention score from bounded features."""
        total = 0.0
        for key, weight in self.WEIGHTS.items():
            total += _clamp(breakdown.get(key, 0.0)) * weight
        return _clamp(total)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
