from __future__ import annotations

from benchmark.metrics import (
    BenchmarkScores,
    evaluate_efficiency_case,
    evaluate_query_result,
    summarize_efficiency_scores,
    summarize_query_scores,
)


def test_evaluate_query_result_counts_hit_mrr_and_false_positive() -> None:
    score = evaluate_query_result(
        expected_memory_ids=["mem-target"],
        expected_keywords=["支付模块回滚"],
        must_not_keywords=["API网关"],
        actual_results=[
            {
                "memory_id": "mem-noise",
                "summary_text": "API网关方案选择: 采用 Nginx",
            },
            {
                "memory_id": "mem-target",
                "summary_text": "支付模块回滚: 立即回滚到 v2.1",
            },
        ],
        k=3,
    )

    assert score.hit_at_k == 1.0
    assert score.mrr == 0.5
    assert score.false_positive == 1.0
    assert score.matched_rank == 2


def test_evaluate_query_result_matches_expected_keywords_without_memory_id() -> None:
    score = evaluate_query_result(
        expected_memory_ids=[],
        expected_keywords=["GraphQL", "否决"],
        must_not_keywords=[],
        actual_results=[
            {
                "memory_id": "mem-1",
                "summary_text": "GraphQL引入决策: 否决 GraphQL 引入",
            }
        ],
        k=3,
    )

    assert score.hit_at_k == 1.0
    assert score.mrr == 1.0
    assert score.matched_rank == 1


def test_summarize_query_scores_averages_metrics() -> None:
    summary = summarize_query_scores(
        [
            BenchmarkScores(hit_at_k=1.0, mrr=1.0, false_positive=0.0),
            BenchmarkScores(hit_at_k=0.0, mrr=0.0, false_positive=1.0),
        ]
    )

    assert summary["hit_at_k"] == 0.5
    assert summary["mrr"] == 0.5
    assert summary["false_positive_rate"] == 0.5


def test_evaluate_efficiency_case_computes_saved_chars_and_steps() -> None:
    score = evaluate_efficiency_case(
        {
            "case_id": "eff-1",
            "baseline_chars": 50,
            "assisted_chars": 10,
            "baseline_steps": 5,
            "assisted_steps": 2,
        }
    )

    assert score["case_id"] == "eff-1"
    assert score["saved_chars"] == 40
    assert score["char_saving_rate"] == 0.8
    assert score["saved_steps"] == 3
    assert score["step_saving_rate"] == 0.6


def test_summarize_efficiency_scores_averages_saving_rates() -> None:
    summary = summarize_efficiency_scores(
        [
            {"char_saving_rate": 0.8, "step_saving_rate": 0.6},
            {"char_saving_rate": 0.4, "step_saving_rate": 0.2},
        ]
    )

    assert summary["case_count"] == 2
    assert summary["avg_char_saving_rate"] == 0.6
    assert summary["avg_step_saving_rate"] == 0.4
