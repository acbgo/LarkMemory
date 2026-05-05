from __future__ import annotations

import logging
import re
import shlex
from typing import Any, Callable

from src.retrieval import RankedMemory

from .types import BenchmarkCase, CaseResult, MetricResult

logger = logging.getLogger(__name__)

ScorerFn = Callable[["ScoringContext"], float]
SCORER_REGISTRY: dict[str, ScorerFn] = {}

METRIC_TARGETS: dict[str, float] = {
    "recall_at_3": 0.85,
    "keyword_match": 0.80,
    "evidence_match": 0.80,
    "should_not_contain_match": 0.90,
    "noise_robustness": 0.80,
    "latest_value_accuracy": 0.90,
    "old_value_suppression": 0.90,
    "char_saving_rate": 0.50,
    "step_saving_rate": 0.50,
    "long_term_recall": 0.70,
    "top1_hit": 0.85,
    "command_exact_match": 0.70,
    "decision_match": 0.85,
    "reason_match": 0.80,
    "rejected_option_match": 0.75,
    "preference_match": 0.85,
    "condition_match": 0.80,
    "expired_memory_suppression": 0.90,
    "freshness_accuracy": 0.85,
    "abstention_accuracy": 0.90,
    "hallucination_rate": 0.10,
    "scope_accuracy": 0.90,
    "cross_project_leakage_rate": 0.10,
}


class ScoringContext:
    __slots__ = ("case", "ranked_memories", "response_text", "evidence_ids")

    def __init__(
        self,
        case: BenchmarkCase,
        ranked_memories: list[RankedMemory],
    ) -> None:
        self.case = case
        self.ranked_memories = ranked_memories
        self.response_text = " ".join(
            r.item.content_text for r in ranked_memories
        ).lower()
        self.evidence_ids = [
            (getattr(r.item, "extra", {}) or {}).get("source_event_id", "")
            for r in ranked_memories
        ]


def register(metric_id: str) -> Callable[[ScorerFn], ScorerFn]:
    def decorator(fn: ScorerFn) -> ScorerFn:
        SCORER_REGISTRY[metric_id] = fn
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Generic metrics
# ---------------------------------------------------------------------------

@register("recall_at_3")
def score_recall_at_3(ctx: ScoringContext) -> float:
    expected_ids = set(ctx.case.expected.get("evidence_event_ids", []))
    if not expected_ids:
        return 0.0
    top3_ids = ctx.evidence_ids[:3]
    return 1.0 if any(eid in expected_ids for eid in top3_ids if eid) else 0.0


@register("keyword_match")
def score_keyword_match(ctx: ScoringContext) -> float:
    keywords = ctx.case.expected.get("answer_keywords", [])
    if not keywords:
        return 0.0
    matched = sum(1 for kw in keywords if kw.lower() in ctx.response_text)
    return matched / len(keywords)


@register("evidence_match")
def score_evidence_match(ctx: ScoringContext) -> float:
    expected_ids = set(ctx.case.expected.get("evidence_event_ids", []))
    if not expected_ids:
        return 0.0
    found_ids = set(eid for eid in ctx.evidence_ids if eid)
    return 1.0 if found_ids & expected_ids else 0.0


@register("should_not_contain_match")
def score_should_not_contain_match(ctx: ScoringContext) -> float:
    forbidden = list(ctx.case.expected.get("forbidden_active_values", []))
    forbidden.extend(ctx.case.expected.get("should_not_contain", []))
    if not forbidden:
        return 1.0
    hits = sum(1 for f in forbidden if f.lower() in ctx.response_text)
    return 1.0 if hits == 0 else 0.0


# ---------------------------------------------------------------------------
# Anti-interference
# ---------------------------------------------------------------------------

@register("noise_robustness")
def score_noise_robustness(ctx: ScoringContext) -> float:
    ev = score_evidence_match(ctx)
    kw = score_keyword_match(ctx)
    return ev * kw


# ---------------------------------------------------------------------------
# Contradiction update
# ---------------------------------------------------------------------------

@register("latest_value_accuracy")
def score_latest_value_accuracy(ctx: ScoringContext) -> float:
    current = ctx.case.expected.get("current_value", "")
    if not current:
        return 1.0
    return 1.0 if current.lower() in ctx.response_text else 0.0


@register("old_value_suppression")
def score_old_value_suppression(ctx: ScoringContext) -> float:
    forbidden = list(ctx.case.expected.get("forbidden_active_values", []))
    inactive = ctx.case.expected.get("inactive_values", [])
    forbidden.extend(inactive)
    if not forbidden:
        return 1.0
    hits = sum(1 for f in forbidden if f.lower() in ctx.response_text)
    return 1.0 if hits == 0 else 0.0


# ---------------------------------------------------------------------------
# Efficiency
# ---------------------------------------------------------------------------

@register("char_saving_rate")
def score_char_saving_rate(ctx: ScoringContext) -> float:
    baseline = ctx.case.expected.get("baseline_chars", 0)
    actual = ctx.case.expected.get("actual_chars", 0)
    if baseline <= 0:
        return 0.0
    saving = 1.0 - (actual / baseline)
    min_rate = ctx.case.expected.get("min_saving_rate", 0.5)
    return 1.0 if saving >= min_rate else saving / min_rate


@register("step_saving_rate")
def score_step_saving_rate(ctx: ScoringContext) -> float:
    baseline = ctx.case.expected.get("baseline_steps", 0)
    actual = ctx.case.expected.get("actual_steps", 0)
    if baseline <= 0:
        return 0.0
    saving = 1.0 - (actual / baseline)
    min_rate = ctx.case.expected.get("min_saving_rate", 0.5)
    return 1.0 if saving >= min_rate else saving / min_rate


# ---------------------------------------------------------------------------
# Long-term retention
# ---------------------------------------------------------------------------

@register("long_term_recall")
def score_long_term_recall(ctx: ScoringContext) -> float:
    if ctx.case.time_span_days <= 30:
        return 1.0
    return score_recall_at_3(ctx)


# ---------------------------------------------------------------------------
# Command memory
# ---------------------------------------------------------------------------

@register("top1_hit")
def score_top1_hit(ctx: ScoringContext) -> float:
    suggested = ctx.case.expected.get("suggested_command", "")
    if not suggested or not ctx.ranked_memories:
        return 0.0
    top_text = _command_output_text(ctx.ranked_memories[0])
    return 1.0 if _commands_equivalent(suggested, top_text) else 0.0


@register("command_exact_match")
def score_command_exact_match(ctx: ScoringContext) -> float:
    suggested = ctx.case.expected.get("suggested_command", "")
    if not suggested or not ctx.ranked_memories:
        return 0.0
    top_text = _command_output_text(ctx.ranked_memories[0])
    return 1.0 if _commands_equivalent(suggested, top_text) else 0.0


def _command_output_text(ranked: RankedMemory) -> str:
    """Return the command-facing output for CLI workflow scoring."""
    workflow = (ranked.item.extra or {}).get("workflow") or {}
    if isinstance(workflow, dict):
        template = str(workflow.get("command_template") or "")
        if template:
            return _render_command_template(template, workflow.get("parameter_bindings") or [])
    return ranked.item.content_text


def _render_command_template(template: str, bindings: Any) -> str:
    """Render `{param}` placeholders with stored CLI parameter values."""
    values: dict[str, str] = {}
    if isinstance(bindings, list):
        for binding in bindings:
            if isinstance(binding, dict):
                name = binding.get("param_name")
                value = binding.get("param_value")
            else:
                name = getattr(binding, "param_name", None)
                value = getattr(binding, "param_value", None)
            if name is not None and value is not None:
                values[str(name)] = str(value)

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        return values.get(name, match.group(0))

    return re.sub(r"\{([^{}]+)\}", replace, template)


def _commands_equivalent(expected: str, actual: str) -> bool:
    """Compare commands while allowing equivalent absolute/relative script paths."""
    expected_tokens = _split_command(expected)
    actual_tokens = _split_command(actual)
    if len(expected_tokens) != len(actual_tokens):
        return False
    return all(
        _command_token_equivalent(exp, act)
        for exp, act in zip(expected_tokens, actual_tokens)
    )


def _split_command(command: str) -> list[str]:
    normalized = command.strip().replace("\\", "/")
    try:
        return shlex.split(normalized)
    except ValueError:
        return normalized.split()


def _command_token_equivalent(expected: str, actual: str) -> bool:
    if expected == actual:
        return True
    exp = expected.replace("\\", "/").lower()
    act = actual.replace("\\", "/").lower()
    if "/" in exp or "/" in act:
        return act.endswith(exp) or exp.endswith(act)
    return False


# ---------------------------------------------------------------------------
# Decision memory
# ---------------------------------------------------------------------------

@register("decision_match")
def score_decision_match(ctx: ScoringContext) -> float:
    current = ctx.case.expected.get("current_value", "")
    keywords = ctx.case.expected.get("answer_keywords", [])
    if current and current.lower() in ctx.response_text:
        return 1.0
    if keywords:
        return 1.0 if any(kw.lower() in ctx.response_text for kw in keywords[:2]) else 0.0
    return 0.0


@register("reason_match")
def score_reason_match(ctx: ScoringContext) -> float:
    keywords = ctx.case.expected.get("answer_keywords", [])
    if len(keywords) < 2:
        return 0.0
    reason_kws = keywords[1:]
    matched = sum(1 for kw in reason_kws if kw.lower() in ctx.response_text)
    return matched / len(reason_kws) if reason_kws else 0.0


@register("rejected_option_match")
def score_rejected_option_match(ctx: ScoringContext) -> float:
    inactive = ctx.case.expected.get("inactive_values", [])
    if not inactive:
        return 1.0
    mentioned = sum(1 for v in inactive if v.lower() in ctx.response_text)
    return 1.0 if mentioned > 0 else 0.0


# ---------------------------------------------------------------------------
# Preference memory
# ---------------------------------------------------------------------------

@register("preference_match")
def score_preference_match(ctx: ScoringContext) -> float:
    current = ctx.case.expected.get("current_value", "")
    keywords = ctx.case.expected.get("answer_keywords", [])
    if current and current.lower() in ctx.response_text:
        return 1.0
    if keywords:
        return 1.0 if any(kw.lower() in ctx.response_text for kw in keywords) else 0.0
    return 0.0


@register("condition_match")
def score_condition_match(ctx: ScoringContext) -> float:
    keywords = ctx.case.expected.get("answer_keywords", [])
    if len(keywords) < 2:
        return 0.0
    condition_kws = keywords[1:]
    matched = sum(1 for kw in condition_kws if kw.lower() in ctx.response_text)
    return matched / len(condition_kws) if condition_kws else 0.0


# ---------------------------------------------------------------------------
# Knowledge health
# ---------------------------------------------------------------------------

@register("expired_memory_suppression")
def score_expired_memory_suppression(ctx: ScoringContext) -> float:
    forbidden = list(ctx.case.expected.get("forbidden_active_values", []))
    forbidden.extend(ctx.case.expected.get("inactive_values", []))
    if not forbidden:
        return 1.0
    hits = sum(1 for f in forbidden if f.lower() in ctx.response_text)
    return 1.0 if hits == 0 else 0.0


@register("freshness_accuracy")
def score_freshness_accuracy(ctx: ScoringContext) -> float:
    current = ctx.case.expected.get("current_value", "")
    if not current:
        return score_keyword_match(ctx)
    return 1.0 if current.lower() in ctx.response_text else 0.0


# ---------------------------------------------------------------------------
# Abstention
# ---------------------------------------------------------------------------

@register("abstention_accuracy")
def score_abstention_accuracy(ctx: ScoringContext) -> float:
    should_retrieve = ctx.case.expected.get("should_retrieve", True)
    if should_retrieve:
        return 1.0
    abstention_kws = ctx.case.expected.get("abstention_keywords", [])
    if not abstention_kws:
        return 1.0 if not ctx.ranked_memories else 0.0
    has_abstention = any(kw.lower() in ctx.response_text for kw in abstention_kws)
    no_results = len(ctx.ranked_memories) == 0
    return 1.0 if (has_abstention or no_results) else 0.0


@register("hallucination_rate")
def score_hallucination_rate(ctx: ScoringContext) -> float:
    triggers = ctx.case.expected.get("hallucination_triggers", [])
    if not triggers:
        return 1.0
    hits = sum(1 for t in triggers if t.lower() in ctx.response_text)
    return 0.0 if hits > 0 else 1.0


# ---------------------------------------------------------------------------
# Cross-project
# ---------------------------------------------------------------------------

@register("scope_accuracy")
def score_scope_accuracy(ctx: ScoringContext) -> float:
    forbidden = ctx.case.expected.get("forbidden_active_values", [])
    if not forbidden:
        forbidden = []
    inactive = ctx.case.expected.get("inactive_values", [])
    all_forbidden = set(f.lower() for f in [*forbidden, *inactive])
    if not all_forbidden:
        return 1.0
    hits = sum(1 for f in all_forbidden if f in ctx.response_text)
    return 1.0 if hits == 0 else 0.0


@register("cross_project_leakage_rate")
def score_cross_project_leakage_rate(ctx: ScoringContext) -> float:
    forbidden = ctx.case.expected.get("forbidden_active_values", [])
    inactive = ctx.case.expected.get("inactive_values", [])
    all_forbidden = set(f.lower() for f in [*forbidden, *inactive])
    if not all_forbidden:
        return 1.0
    hits = sum(1 for f in all_forbidden if f in ctx.response_text)
    return 0.0 if hits > 0 else 1.0


# ---------------------------------------------------------------------------
# Case-level scoring
# ---------------------------------------------------------------------------

def score_case(
    case: BenchmarkCase,
    ranked_memories: list[RankedMemory],
) -> CaseResult:
    ctx = ScoringContext(case, ranked_memories)
    metric_results: list[MetricResult] = []

    for metric_id in case.metrics:
        scorer_fn = SCORER_REGISTRY.get(metric_id)
        if scorer_fn is None:
            logger.warning("Unknown metric '%s' for case %s", metric_id, case.case_id)
            metric_results.append(MetricResult(metric_id=metric_id, value=0.0, passed=False))
            continue
        try:
            value = scorer_fn(ctx)
        except Exception:
            logger.exception("Metric '%s' failed for case %s", metric_id, case.case_id)
            value = 0.0
        target = METRIC_TARGETS.get(metric_id, 0.80)
        passed = value >= target
        metric_results.append(MetricResult(metric_id=metric_id, value=value, passed=passed))

    all_passed = all(mr.passed for mr in metric_results) if metric_results else False

    return CaseResult(
        case_id=case.case_id,
        category=case.category,
        test_type=case.test_type,
        difficulty=case.difficulty,
        metric_results=metric_results,
        response_text=ctx.response_text[:500],
        evidence_event_ids=ctx.evidence_ids[:10],
    )
