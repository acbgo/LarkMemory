from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

TEST_TYPES = [
    "retrieval_recall",
    "anti_interference",
    "contradiction_update",
    "efficiency",
    "long_term_retention",
    "abstention",
    "cross_project",
]

DIRECTION_WEIGHTS: dict[str, float] = {
    "command_memory": 0.15,
    "decision_memory": 0.30,
    "preference_memory": 0.25,
    "knowledge_health": 0.30,
}

DIRECTION_LABELS: dict[str, str] = {
    "command_memory": "A: CLI命令记忆",
    "decision_memory": "B: 飞书决策记忆",
    "preference_memory": "C: 个人偏好记忆",
    "knowledge_health": "D: 团队知识健康",
}


@dataclass(slots=True)
class BenchmarkCase:
    case_id: str
    category: str
    test_type: str
    scenario: str
    difficulty: str
    time_span_days: int
    input_events: list[dict[str, Any]]
    query: str
    expected: dict[str, Any]
    metrics: list[str]


@dataclass(slots=True)
class MetricResult:
    metric_id: str
    value: float
    passed: bool


@dataclass(slots=True)
class CaseResult:
    case_id: str
    category: str
    test_type: str
    difficulty: str
    metric_results: list[MetricResult] = field(default_factory=list)
    error: str | None = None
    response_text: str | None = None
    evidence_event_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TestTypeResult:
    test_type: str
    case_count: int
    passed_count: int
    score: float
    metric_averages: dict[str, float] = field(default_factory=dict)
    cases: list[CaseResult] = field(default_factory=list)


@dataclass(slots=True)
class DirectionResult:
    direction: str
    weight: float
    case_count: int
    passed_count: int
    direction_score: float
    metric_averages: dict[str, float] = field(default_factory=dict)
    cases: list[CaseResult] = field(default_factory=list)


@dataclass(slots=True)
class AblationVariant:
    name: str
    description: str
    disabled_components: list[str] = field(default_factory=list)
    result: BenchmarkRunResult | None = None


@dataclass(slots=True)
class BenchmarkRunResult:
    run_id: str
    suite_name: str
    overall_score: float
    rating: str
    test_type_results: list[TestTypeResult] = field(default_factory=list)
    direction_results: list[DirectionResult] = field(default_factory=list)
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    error_cases: int = 0
    run_duration_seconds: float = 0.0


@dataclass(slots=True)
class RunnerConfig:
    run_id: str
    suite_name: str = "all"
    case_ids: list[str] = field(default_factory=list)
    datasets_dir: str = "benchmark/datasets"
    temp_root: str | None = None
    keep_temp: bool = False
    ablation: bool = False
    progress_callback: Callable[[str, int, int, str, Any | None], None] | None = None
