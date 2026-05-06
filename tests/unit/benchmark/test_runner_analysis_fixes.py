from __future__ import annotations

from benchmark.runner.aggregator import aggregate
from benchmark.runner.reporter import to_json
from benchmark.runner.runner import _extract_project_id
from benchmark.runner.scorer import score_case
from benchmark.runner.types import BenchmarkCase, CaseResult, MetricResult
from src.retrieval import MemoryDomain, MemoryItem, RankedMemory


def _case(
    *,
    case_id: str = "dec_case",
    test_type: str = "contradiction_update",
    expected: dict[str, object] | None = None,
    metrics: list[str] | None = None,
    input_events: list[dict[str, object]] | None = None,
) -> BenchmarkCase:
    return BenchmarkCase(
        case_id=case_id,
        category="decision_memory",
        test_type=test_type,
        scenario="scenario",
        difficulty="medium",
        time_span_days=10,
        input_events=input_events or [],
        query="query",
        expected=expected or {},
        metrics=metrics or [],
    )


def _ranked(text: str, *, source_event_id: str = "e2") -> RankedMemory:
    item = MemoryItem(
        memory_id="mem-1",
        domain=MemoryDomain.PROJECT_DECISION,
        memory_type="project_decision",
        content_text=text,
        extra={"source_event_id": source_event_id},
    )
    return RankedMemory(item=item, final_score=1.0, rank=1)


def test_old_value_suppression_allows_historical_mention_when_current_value_is_top1() -> None:
    case = _case(
        expected={
            "current_value": "Memcached",
            "inactive_values": ["Redis"],
            "forbidden_active_values": ["Redis"],
            "allow_historical_mention": True,
        },
        metrics=["old_value_suppression"],
    )

    result = score_case(
        case,
        [_ranked("缓存层改用 Memcached，Redis 在当前场景下内存占用过高。")],
    )

    assert result.metric_results[0].value == 1.0
    assert result.metric_results[0].passed is True


def test_noise_robustness_for_abstention_uses_refusal_and_hallucination_scores() -> None:
    case = _case(
        test_type="abstention",
        expected={
            "should_retrieve": False,
            "abstention_keywords": ["未找到"],
            "hallucination_triggers": ["React"],
        },
        metrics=["noise_robustness"],
    )

    result = score_case(case, [])

    assert result.metric_results[0].value == 1.0
    assert result.metric_results[0].passed is True


def test_cross_project_query_scope_uses_expected_evidence_project() -> None:
    case = _case(
        input_events=[
            {"event_id": "e1", "context": {"project": "Alpha"}},
            {"event_id": "e2", "context": {"project": "Beta"}},
            {"event_id": "e3", "context": {"project": "Gamma"}},
        ],
        expected={"evidence_event_ids": ["e2"]},
    )

    assert _extract_project_id(case) == "Beta"


def test_cross_project_query_scope_prefers_explicit_query_project_id() -> None:
    case = _case(
        input_events=[
            {"event_id": "e1", "context": {"project": "Alpha"}},
            {"event_id": "e2", "context": {"project": "Beta"}},
        ],
        expected={
            "query_project_id": "QueryScope",
            "evidence_event_ids": ["e2"],
        },
    )

    assert _extract_project_id(case) == "QueryScope"


def test_decision_only_suite_overall_uses_direction_score_without_global_weight() -> None:
    result = aggregate(
        run_id="run-1",
        suite_name="decision_memory",
        case_results=[
            CaseResult(
                case_id="dec-1",
                category="decision_memory",
                test_type="retrieval_recall",
                difficulty="easy",
                metric_results=[MetricResult("recall_at_3", 1.0, True)],
            )
        ],
        duration_seconds=1.0,
    )

    assert result.overall_score == 100.0


def test_report_json_includes_response_text_and_evidence_ids() -> None:
    result = aggregate(
        run_id="run-1",
        suite_name="decision_memory",
        case_results=[
            CaseResult(
                case_id="dec-1",
                category="decision_memory",
                test_type="retrieval_recall",
                difficulty="easy",
                metric_results=[MetricResult("recall_at_3", 1.0, True)],
                response_text="采用方案B",
                evidence_event_ids=["e4"],
            )
        ],
        duration_seconds=1.0,
    )

    case_payload = to_json(result)["cases"][0]

    assert case_payload["response_text"] == "采用方案B"
    assert case_payload["evidence_event_ids"] == ["e4"]
