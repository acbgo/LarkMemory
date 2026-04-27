from __future__ import annotations

from src.domains.project_decision import (
    DecisionRankWeights,
    ProjectDecision,
    ProjectDecisionQuery,
    ProjectDecisionRanker,
    ProjectDecisionSearchResult,
)
from src.retrieval import MemoryDomain, MemoryItem


def _result(
    memory_id: str,
    *,
    topic: str,
    decided_at: str = "2026-04-26T00:00:00Z",
    status: str = "confirmed",
    matched_fields: list[str] | None = None,
    score: float = 0.2,
) -> ProjectDecisionSearchResult:
    decision = ProjectDecision(
        decision_id=memory_id,
        project_id="project-1",
        topic=topic,
        decision="采用方案 B",
        status=status,  # type: ignore[arg-type]
        decided_at=decided_at,
        confidence=0.9,
        importance=0.8,
    )
    item = MemoryItem(
        memory_id=memory_id,
        domain=MemoryDomain.PROJECT_DECISION,
        memory_type="project_decision",
        content_text=decision.build_content_text(),
    )
    return ProjectDecisionSearchResult(
        decision=decision,
        memory_item=item,
        score=score,
        matched_fields=matched_fields or [],
    )


def test_exact_topic_match_ranks_before_fuzzy_match() -> None:
    ranker = ProjectDecisionRanker()
    query = ProjectDecisionQuery(query_text="为什么选方案 B", project_id="project-1", topic="检索层方案")
    exact = _result("mem-exact", topic="检索层方案", matched_fields=["topic", "project_id"])
    fuzzy = _result("mem-fuzzy", topic="架构方案", matched_fields=["query_text"])

    ranked = ranker.rank([fuzzy, exact], query)

    assert ranked[0].decision.decision_id == "mem-exact"


def test_newer_decision_wins_when_relevance_is_close() -> None:
    ranker = ProjectDecisionRanker()
    query = ProjectDecisionQuery(query_text="历史决策", project_id="project-1", topic="检索层方案")
    old = _result("mem-old", topic="检索层方案", decided_at="2026-01-01T00:00:00Z")
    new = _result("mem-new", topic="检索层方案", decided_at="2026-04-20T00:00:00Z")

    ranked = ranker.rank([old, new], query)

    assert ranked[0].decision.decision_id == "mem-new"


def test_superseded_decision_is_penalized() -> None:
    ranker = ProjectDecisionRanker()
    query = ProjectDecisionQuery(query_text="检索层方案", topic="检索层方案")
    active = _result("mem-active", topic="检索层方案")
    superseded = _result("mem-superseded", topic="检索层方案", status="superseded")

    assert ranker.score_result(superseded, query) < ranker.score_result(active, query)


def test_weight_normalization_handles_zero_total() -> None:
    weights = DecisionRankWeights(0, 0, 0, 0, 0).normalized()

    assert weights.relevance == DecisionRankWeights().relevance
