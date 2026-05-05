from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .llm_extractor import TeamRetentionLLMExtraction

TeamRetentionAdmissionStatus = Literal["reject", "candidate", "active"]

CANDIDATE_THRESHOLD = 0.40
ACTIVE_THRESHOLD = 0.70


@dataclass(slots=True)
class TeamRetentionAdmissionDecision:
    status: TeamRetentionAdmissionStatus
    confidence: float
    importance: float
    reason: str


class TeamRetentionAdmissionDecider:
    def decide(
        self,
        extraction: TeamRetentionLLMExtraction,
        *,
        confidence: float,
        importance: float,
    ) -> TeamRetentionAdmissionDecision:
        if not extraction.is_team_retention or not extraction.fact_value:
            return TeamRetentionAdmissionDecision("reject", confidence, importance, "not_team_retention")

        if extraction.certainty == "speculative":
            return TeamRetentionAdmissionDecision("candidate", confidence, importance, "speculative_certainty")

        if extraction.risk_level == "high" and extraction.certainty != "explicit":
            return TeamRetentionAdmissionDecision(
                "candidate", confidence, importance, "high_risk_requires_explicit_evidence"
            )

        if confidence >= ACTIVE_THRESHOLD:
            return TeamRetentionAdmissionDecision("active", confidence, importance, "active_threshold_met")

        if confidence >= CANDIDATE_THRESHOLD:
            return TeamRetentionAdmissionDecision("candidate", confidence, importance, "candidate_threshold")

        return TeamRetentionAdmissionDecision("reject", confidence, importance, "below_candidate_threshold")
