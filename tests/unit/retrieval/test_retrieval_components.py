from __future__ import annotations

import asyncio

from src.retrieval import (
    DomainRecallResult,
    FusedCandidate,
    IntentAnalyzer,
    IntentResult,
    MemoryDomain,
    MemoryItem,
    MemoryScope,
    QueryRewriter,
    ResultFusion,
    RetrievalQuery,
    RewrittenQuery,
    Reranker,
)
from src.retrieval.query_rewrite import _extract_topics_by_rules


def _memory(
    memory_id: str,
    *,
    domain: MemoryDomain = MemoryDomain.PROJECT_DECISION,
    content: str = "团队决定使用方案B",
    scope: MemoryScope = MemoryScope.PROJECT,
    extra: dict[str, str] | None = None,
) -> MemoryItem:
    return MemoryItem(
        memory_id=memory_id,
        domain=domain,
        memory_type="test",
        content_text=content,
        importance=0.5,
        confidence=0.5,
        scope=scope,
        extra=extra or {},
    )


def test_fusion_accumulates_duplicate_recall_evidence() -> None:
    shared = _memory("mem-shared")
    single = _memory("mem-single")

    recalls = [
        DomainRecallResult(
            domain=MemoryDomain.PROJECT_DECISION,
            items=[shared, single],
        ),
        DomainRecallResult(
            domain=MemoryDomain.TEAM_RETENTION,
            items=[shared],
        ),
    ]
    intent = IntentResult(
        primary_domains=[MemoryDomain.PROJECT_DECISION],
        secondary_domains=[MemoryDomain.TEAM_RETENTION],
    )

    result = ResultFusion().fuse(recalls, intent)

    assert result[0].item.memory_id == "mem-shared"
    assert result[0].fusion_score > result[1].fusion_score


def test_reranker_normalizes_domain_weights() -> None:
    reranker = Reranker()

    weights = reranker._get_effective_weights(MemoryDomain.PROJECT_DECISION)

    assert round(sum(weights.values()), 6) == 1


def test_scope_match_requires_exact_user_id() -> None:
    candidate = FusedCandidate(
        item=_memory(
            "mem-user",
            scope=MemoryScope.USER,
            extra={"user_id": "user-a"},
        ),
        source_domain=MemoryDomain.PERSONAL_PREFERENCE,
        fusion_score=0.5,
    )
    query = RewrittenQuery(
        original=RetrievalQuery("按我的习惯来", user_id="user-b"),
        scope_filters={"user_id": "user-b"},
    )

    ranked = asyncio.run(Reranker().rerank([candidate], query, top_k=1))

    assert ranked[0].score_breakdown["scope_match"] == 0


def test_chinese_topic_extraction_keeps_domain_terms() -> None:
    topics = _extract_topics_by_rules("飞书机器人需要检索记忆并注入上下文")

    assert "飞书" in topics
    assert "检索" in topics
    assert "记忆" in topics
    assert "上下文" in topics


class _FakeRewriteLLM:
    async def ajson(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "rewritten_text": "查找项目决策",
            "extracted_topics": ["项目决策"],
            "time_start": None,
            "time_end": None,
            "time_description": None,
            "boost_signals": {"semantic_match": 0.9},
        }


def test_llm_rewrite_merges_rule_boosts() -> None:
    rewriter = QueryRewriter(_FakeRewriteLLM())
    query = RetrievalQuery("为什么选方案B", project_id="project-1")
    intent = IntentResult(primary_domains=[MemoryDomain.PROJECT_DECISION])

    rewritten = asyncio.run(rewriter.rewrite(query, intent))

    assert rewritten.boost_signals["semantic_match"] == 0.9
    assert rewritten.boost_signals["project_match"] == 0.7
    assert rewritten.boost_signals["topic_match"] == 0.8


def test_keyword_fallback_defaults_to_collaboration_domains() -> None:
    result = asyncio.run(IntentAnalyzer().analyze(RetrievalQuery("帮我看看这个问题")))

    assert result.primary_domains == [MemoryDomain.TEAM_RETENTION]
    assert result.secondary_domains == [MemoryDomain.PROJECT_DECISION]
