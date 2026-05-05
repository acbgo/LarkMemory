from __future__ import annotations

import logging
from collections import defaultdict

from .types import (
    BenchmarkRunResult,
    CaseResult,
    DirectionResult,
    DIRECTION_LABELS,
    DIRECTION_WEIGHTS,
    TestTypeResult,
)

logger = logging.getLogger(__name__)


def _rating(score: float) -> str:
    if score >= 85:
        return "优秀"
    elif score >= 70:
        return "良好"
    else:
        return "待改进"


def aggregate(
    run_id: str,
    suite_name: str,
    case_results: list[CaseResult],
    duration_seconds: float,
) -> BenchmarkRunResult:
    """Aggregate case results by test_type and by direction, compute overall score."""

    # --- Group by test_type ---
    by_test_type: dict[str, list[CaseResult]] = defaultdict(list)
    for cr in case_results:
        by_test_type[cr.test_type].append(cr)

    test_type_results: list[TestTypeResult] = []
    for tt in ["retrieval_recall", "anti_interference", "contradiction_update",
                "efficiency", "long_term_retention", "abstention", "cross_project"]:
        cases = by_test_type.get(tt, [])
        if not cases:
            continue

        metric_values: dict[str, list[float]] = defaultdict(list)
        tt_passed = 0
        for cr in cases:
            if cr.error:
                continue
            for mr in cr.metric_results:
                metric_values[mr.metric_id].append(mr.value)
            if cr.metric_results and all(mr.passed for mr in cr.metric_results):
                tt_passed += 1

        metric_averages = {mid: round(sum(vals) / len(vals), 4) for mid, vals in metric_values.items()}
        all_vals = [v for vals in metric_values.values() for v in vals]
        tt_score = round(sum(all_vals) / len(all_vals), 4) if all_vals else 0.0

        test_type_results.append(TestTypeResult(
            test_type=tt,
            case_count=len(cases),
            passed_count=tt_passed,
            score=tt_score,
            metric_averages=metric_averages,
            cases=cases,
        ))

    # --- Group by direction ---
    by_direction: dict[str, list[CaseResult]] = defaultdict(list)
    for cr in case_results:
        by_direction[cr.category].append(cr)

    direction_results: list[DirectionResult] = []
    total_passed = 0
    total_failed = 0
    total_error = 0

    for direction in ["command_memory", "decision_memory", "preference_memory", "knowledge_health"]:
        cases = by_direction.get(direction, [])
        if not cases:
            continue

        weight = DIRECTION_WEIGHTS.get(direction, 0.25)
        metric_values: dict[str, list[float]] = defaultdict(list)
        dir_passed = 0
        dir_error = 0
        for cr in cases:
            if cr.error:
                dir_error += 1
                total_error += 1
                continue
            for mr in cr.metric_results:
                metric_values[mr.metric_id].append(mr.value)
            if cr.metric_results and all(mr.passed for mr in cr.metric_results):
                dir_passed += 1

        total_passed += dir_passed
        total_failed += len(cases) - dir_passed - dir_error

        metric_averages = {mid: round(sum(vals) / len(vals), 4) for mid, vals in metric_values.items()}
        all_vals = [v for vals in metric_values.values() for v in vals]
        dir_score = round(sum(all_vals) / len(all_vals), 4) if all_vals else 0.0

        direction_results.append(DirectionResult(
            direction=direction,
            weight=weight,
            case_count=len(cases),
            passed_count=dir_passed,
            direction_score=dir_score,
            metric_averages=metric_averages,
            cases=cases,
        ))

    # Overall score = Σ(direction_score × weight) × 100
    overall = sum(
        dr.direction_score * dr.weight
        for dr in direction_results
    ) * 100

    return BenchmarkRunResult(
        run_id=run_id,
        suite_name=suite_name,
        overall_score=round(overall, 1),
        rating=_rating(overall),
        test_type_results=test_type_results,
        direction_results=direction_results,
        total_cases=len(case_results),
        passed_cases=total_passed,
        failed_cases=total_failed,
        error_cases=total_error,
        run_duration_seconds=round(duration_seconds, 2),
    )
