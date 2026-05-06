from __future__ import annotations

import json
import logging
from typing import Any

from .types import BenchmarkRunResult, DirectionResult, TestTypeResult, DIRECTION_LABELS

logger = logging.getLogger(__name__)

TEST_TYPE_LABELS: dict[str, str] = {
    "retrieval_recall": "基础召回",
    "anti_interference": "抗干扰",
    "contradiction_update": "矛盾更新",
    "efficiency": "效能验证",
    "long_term_retention": "长时序记忆",
    "abstention": "拒答/防幻觉",
    "cross_project": "跨项目隔离",
}


def to_json(result: BenchmarkRunResult) -> dict[str, Any]:
    """Convert result to a JSON-serializable dict for API responses."""
    return {
        "run_id": result.run_id,
        "suite_name": result.suite_name,
        "overall_score": result.overall_score,
        "rating": result.rating,
        "summary": {
            "total_cases": result.total_cases,
            "passed_cases": result.passed_cases,
            "failed_cases": result.failed_cases,
            "error_cases": result.error_cases,
            "pass_rate": round(result.passed_cases / result.total_cases * 100, 1) if result.total_cases else 0,
            "run_duration_seconds": result.run_duration_seconds,
        },
        "by_test_type": [
            {
                "test_type": ttr.test_type,
                "label": TEST_TYPE_LABELS.get(ttr.test_type, ttr.test_type),
                "case_count": ttr.case_count,
                "passed_count": ttr.passed_count,
                "pass_rate": round(ttr.passed_count / ttr.case_count * 100, 1) if ttr.case_count else 0,
                "score": round(ttr.score * 100, 1),
                "metric_averages": ttr.metric_averages,
            }
            for ttr in result.test_type_results
        ],
        "by_direction": [
            {
                "direction": dr.direction,
                "label": DIRECTION_LABELS.get(dr.direction, dr.direction),
                "weight": dr.weight,
                "case_count": dr.case_count,
                "passed_count": dr.passed_count,
                "score": round(dr.direction_score * 100, 1),
                "metric_averages": dr.metric_averages,
            }
            for dr in result.direction_results
        ],
        "cases": [
            {
                "case_id": c.case_id,
                "category": c.category,
                "test_type": c.test_type,
                "difficulty": c.difficulty,
                "passed": all(mr.passed for mr in c.metric_results) if c.metric_results else False,
                "error": c.error,
                "response_text": c.response_text,
                "evidence_event_ids": list(c.evidence_event_ids),
                "metrics": {mr.metric_id: {"value": mr.value, "passed": mr.passed} for mr in c.metric_results},
            }
            for ttr in result.test_type_results
            for c in ttr.cases
        ],
    }


def to_markdown(result: BenchmarkRunResult) -> str:
    """Generate a Markdown report string."""
    lines: list[str] = []

    lines.append("# LarkMemory Benchmark 评测报告")
    lines.append("")
    lines.append(f"**Run ID**: `{result.run_id}`")
    lines.append(f"**Suite**: {result.suite_name}")
    lines.append(f"**耗时**: {result.run_duration_seconds}s")
    lines.append("")

    # Overall
    lines.append("## 总体结果")
    lines.append("")
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 总分 | **{result.overall_score}** / 100 |")
    lines.append(f"| 评级 | **{result.rating}** |")
    lines.append(f"| 总用例 | {result.total_cases} |")
    lines.append(f"| 通过 | {result.passed_cases} |")
    lines.append(f"| 失败 | {result.failed_cases} |")
    lines.append(f"| 错误 | {result.error_cases} |")
    pass_rate = round(result.passed_cases / result.total_cases * 100, 1) if result.total_cases else 0
    lines.append(f"| 通过率 | {pass_rate}% |")
    lines.append("")

    # By test type
    lines.append("## 按测试类型")
    lines.append("")
    lines.append("| 测试类型 | 用例数 | 通过 | 通过率 | 得分 |")
    lines.append("|---------|--------|------|--------|------|")
    for ttr in result.test_type_results:
        pr = round(ttr.passed_count / ttr.case_count * 100, 1) if ttr.case_count else 0
        label = TEST_TYPE_LABELS.get(ttr.test_type, ttr.test_type)
        lines.append(f"| {label} ({ttr.test_type}) | {ttr.case_count} | {ttr.passed_count} | {pr}% | {round(ttr.score * 100, 1)} |")
    lines.append("")

    # By direction
    lines.append("## 按比赛方向")
    lines.append("")
    lines.append("| 方向 | 权重 | 用例数 | 通过 | 得分 | 加权贡献 |")
    lines.append("|------|------|--------|------|------|---------|")
    for dr in result.direction_results:
        label = DIRECTION_LABELS.get(dr.direction, dr.direction)
        weighted = round(dr.direction_score * dr.weight * 100, 1)
        lines.append(f"| {label} | {dr.weight} | {dr.case_count} | {dr.passed_count} | {round(dr.direction_score * 100, 1)} | {weighted} |")
    lines.append("")

    # Per-case detail
    lines.append("## 用例详情")
    lines.append("")
    lines.append("| case_id | 方向 | 测试类型 | 难度 | 结果 | 指标详情 |")
    lines.append("|---------|------|---------|------|------|---------|")
    for ttr in result.test_type_results:
        for c in ttr.cases:
            if c.error:
                status = f"❌ {c.error[:50]}"
            elif c.metric_results and all(mr.passed for mr in c.metric_results):
                status = "✅"
            else:
                status = "❌"
            metric_detail = ", ".join(
                f"{mr.metric_id}={mr.value:.2f}" + ("✓" if mr.passed else "✗")
                for mr in c.metric_results
            )
            lines.append(f"| {c.case_id} | {c.category} | {c.test_type} | {c.difficulty} | {status} | {metric_detail[:100]} |")

    return "\n".join(lines)


def save_report(result: BenchmarkRunResult, path: str) -> None:
    """Save JSON and Markdown reports to the specified directory."""
    import os
    os.makedirs(path, exist_ok=True)

    json_path = os.path.join(path, f"{result.run_id}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(to_json(result), f, ensure_ascii=False, indent=2)
    logger.info("JSON report saved to %s", json_path)

    md_path = os.path.join(path, f"{result.run_id}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(to_markdown(result))
    logger.info("Markdown report saved to %s", md_path)
