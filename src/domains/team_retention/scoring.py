from __future__ import annotations

from .llm_extractor import TeamRetentionLLMExtraction

CERTAINTY_BASE: dict[str, float] = {
    "explicit": 0.75,
    "inferred": 0.50,
    "speculative": 0.20,
}

EVIDENCE_BONUS: dict[str, float] = {
    "direct_quote": 0.15,
    "paraphrased": 0.0,
    "implied": -0.10,
}

SPECIFICITY_BONUS: dict[str, float] = {
    "specific": 0.10,
    "general": 0.0,
    "vague": -0.10,
}

RISK_WEIGHT: dict[str, float] = {
    "high": 0.35,
    "medium": 0.15,
    "low": 0.05,
}

TIME_WEIGHT: dict[str, float] = {
    "urgent": 0.30,
    "near_term": 0.15,
    "stable": 0.0,
}

SCOPE_WEIGHT: dict[str, float] = {
    "team_wide": 0.20,
    "project": 0.12,
    "individual": 0.05,
}

IRREVERSIBILITY_WEIGHT: dict[str, float] = {
    "irreversible": 0.15,
    "reversible": 0.08,
    "low_cost": 0.0,
}


def calculate_confidence(extraction: TeamRetentionLLMExtraction) -> float:
    base = CERTAINTY_BASE.get(extraction.certainty, 0.30)
    evidence = EVIDENCE_BONUS.get(extraction.evidence_quality, 0.0)
    specificity = SPECIFICITY_BONUS.get(extraction.fact_specificity, 0.0)
    return _clamp(base + evidence + specificity)


def calculate_importance(extraction: TeamRetentionLLMExtraction) -> float:
    risk = RISK_WEIGHT.get(extraction.risk_level, 0.10)
    time = TIME_WEIGHT.get(extraction.time_sensitivity, 0.05)
    scope = SCOPE_WEIGHT.get(extraction.scope_impact, 0.05)
    irrev = IRREVERSIBILITY_WEIGHT.get(extraction.irreversibility, 0.0)
    return _clamp(risk + time + scope + irrev)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
