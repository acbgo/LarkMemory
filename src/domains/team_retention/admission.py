from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.schemas import NormalizedEvent

from .llm_extractor import TeamRetentionLLMExtraction
from .preprocessor import TeamRetentionPreprocessResult


TeamRetentionAdmissionStatus = Literal["reject", "candidate", "active"]


@dataclass(slots=True)
class TeamRetentionAdmissionDecision:
    status: TeamRetentionAdmissionStatus
    score: float
    confidence: float
    importance: float
    reason: str
    breakdown: dict[str, float] | None = None
    blockers: list[str] | None = None


class TeamRetentionAdmissionDecider:
    """Make backend-owned TeamRetention admission decisions from extracted facts."""

    CANDIDATE_THRESHOLD = 0.35
    ACTIVE_THRESHOLD = 0.72

    def decide(
        self,
        extraction: TeamRetentionLLMExtraction,
        *,
        event: NormalizedEvent | None = None,
        preprocess: TeamRetentionPreprocessResult | None = None,
        sensitive_unmasked: bool = False,
    ) -> TeamRetentionAdmissionDecision:
        """Return final status using deterministic, explainable backend policy."""
        score, breakdown = self.score(extraction, event=event, preprocess=preprocess)
        confidence = _clamp(extraction.confidence or score)
        importance = _clamp(extraction.importance or score)
        blockers = self._active_blockers(extraction, event=event, sensitive_unmasked=sensitive_unmasked)
        if not extraction.is_team_retention_memory or not extraction.fact_value:
            return TeamRetentionAdmissionDecision("reject", score, confidence, importance, "not_team_retention", breakdown, blockers)
        if score < self.CANDIDATE_THRESHOLD:
            if extraction.evidence_text:
                return TeamRetentionAdmissionDecision("candidate", score, confidence, importance, "low_score_but_extractable_fact", breakdown, blockers)
            return TeamRetentionAdmissionDecision("reject", score, confidence, importance, "score_below_candidate", breakdown, blockers)
        if score >= self.ACTIVE_THRESHOLD and not blockers:
            return TeamRetentionAdmissionDecision("active", score, confidence, importance, "active_threshold_met", breakdown, blockers)
        return TeamRetentionAdmissionDecision("candidate", score, confidence, importance, "candidate_or_downgraded", breakdown, blockers)

    def score(
        self,
        extraction: TeamRetentionLLMExtraction,
        *,
        event: NormalizedEvent | None = None,
        preprocess: TeamRetentionPreprocessResult | None = None,
    ) -> tuple[float, dict[str, float]]:
        """Compute an explainable admission score without relying on LLM self-scores."""
        features = preprocess.features if preprocess is not None else None
        has_scope = bool(
            event is not None
            and (event.context.team_id or event.context.project_id or event.context.workspace_id)
        )
        breakdown: dict[str, float] = {}
        breakdown["candidate_signal"] = 0.25 if extraction.is_team_retention_memory else 0.0
        breakdown["certainty"] = {"explicit": 0.20, "inferred": 0.08, "speculative": -0.20}.get(extraction.certainty, 0.0)
        breakdown["stability"] = {"stable": 0.15, "unknown": 0.03, "temporary": -0.15}.get(extraction.stability, 0.0)
        breakdown["actionability"] = {"actionable": 0.15, "informational": 0.05, "unclear": 0.0}.get(extraction.actionability, 0.0)
        breakdown["risk"] = {"high": 0.20, "medium": 0.10, "low": 0.03}.get(extraction.risk_level, 0.03)
        breakdown["scope"] = 0.10 if has_scope else 0.0
        breakdown["entity"] = 0.05 if self._has_entity(extraction) else 0.0
        breakdown["evidence"] = 0.05 if extraction.evidence_text else 0.0
        breakdown["explicit_rule_hint"] = 0.08 if features and features.explicit_memory_keywords else 0.0
        breakdown["future_rule_hint"] = 0.05 if features and features.future_keywords else 0.0
        breakdown["uncertainty_penalty"] = -0.20 if features and features.uncertainty_markers else 0.0
        breakdown["needs_confirmation_penalty"] = -0.20 if extraction.needs_confirmation else 0.0
        total = sum(breakdown.values())
        return _clamp(total), breakdown

    def _active_blockers(
        self,
        extraction: TeamRetentionLLMExtraction,
        *,
        event: NormalizedEvent | None,
        sensitive_unmasked: bool,
    ) -> list[str]:
        blockers: list[str] = []
        if event is None or not (event.context.team_id or event.context.project_id or event.context.workspace_id):
            blockers.append("missing_scope")
        if extraction.certainty == "speculative":
            blockers.append("speculative")
        if extraction.stability in {"temporary", "unknown"}:
            blockers.append(f"stability_{extraction.stability}")
        if extraction.actionability == "unclear":
            blockers.append("unclear_actionability")
        if extraction.needs_confirmation:
            blockers.append("needs_confirmation")
        if sensitive_unmasked:
            blockers.append("sensitive_unmasked")
        if extraction.risk_level == "high" and extraction.certainty != "explicit":
            blockers.append("high_risk_requires_explicit_evidence")
        return blockers

    def _has_entity(self, extraction: TeamRetentionLLMExtraction) -> bool:
        entity = extraction.primary_entity
        return bool(entity.get("normalized_key") or entity.get("name") or extraction.topic_key or extraction.version_group_hint)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
