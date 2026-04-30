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
    RetrievalTracer,
    RewrittenQuery,
    Reranker,
    memory_item_from_core,
)
from src.retrieval.query_rewrite import _extract_topics_by_rules
from src.schemas import MemoryCore


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
    async def atext(self, *_args: object, **_kwargs: object) -> str:
        return "查询项目中为什么选择方案 B 的历史决策和理由"


class _FakeIntentLLM:
    async def atext(self, *_args: object, **_kwargs: object) -> str:
        return "project_decision"


class _FakeNoisyIntentLLM:
    async def atext(self, *_args: object, **_kwargs: object) -> str:
        return "类别: project_decision"


def test_llm_rewrite_returns_plain_query_and_keeps_rule_boosts() -> None:
    rewriter = QueryRewriter(_FakeRewriteLLM())
    query = RetrievalQuery("为什么选方案B", project_id="project-1")
    intent = IntentResult(primary_domains=[MemoryDomain.PROJECT_DECISION])

    rewritten = asyncio.run(rewriter.rewrite(query, intent))

    assert rewritten.rewritten_text == "查询项目中为什么选择方案 B 的历史决策和理由"
    assert rewritten.boost_signals["project_match"] == 0.7
    assert rewritten.boost_signals["topic_match"] == 0.8


def test_llm_rewrite_preserves_rule_topics_scope_and_time_window() -> None:
    rewriter = QueryRewriter(_FakeRewriteLLM())
    query = RetrievalQuery("为什么选方案B", project_id="project-1")
    intent = IntentResult(
        primary_domains=[MemoryDomain.PROJECT_DECISION],
        keywords=["方案B"],
        time_hint="last_week",
    )

    rewritten = asyncio.run(rewriter.rewrite(query, intent))

    assert rewritten.rewritten_text == "查询项目中为什么选择方案 B 的历史决策和理由"
    assert "方案B" in rewritten.extracted_topics
    assert rewritten.time_window is not None
    assert rewritten.scope_filters == {"project_id": "project-1"}
    assert rewritten.boost_signals["project_match"] == 0.7
    assert rewritten.boost_signals["topic_match"] == 0.8


def test_keyword_fallback_defaults_to_collaboration_domains() -> None:
    result = asyncio.run(IntentAnalyzer().analyze(RetrievalQuery("帮我看看这个问题")))

    assert result.primary_domains == [MemoryDomain.TEAM_RETENTION]
    assert result.secondary_domains == [MemoryDomain.PROJECT_DECISION]


def test_intent_analyzer_uses_single_four_class_label() -> None:
    result = asyncio.run(IntentAnalyzer(_FakeIntentLLM()).analyze(RetrievalQuery("为什么选方案B")))

    assert result.primary_domains == [MemoryDomain.PROJECT_DECISION]
    assert result.secondary_domains == [MemoryDomain.TEAM_RETENTION]
    assert result.intent_type == "project_decision"
    assert result.keywords == ["为什么", "方案"]
    assert result.confidence == 0.8


def test_intent_analyzer_accepts_label_with_extra_text() -> None:
    result = asyncio.run(IntentAnalyzer(_FakeNoisyIntentLLM()).analyze(RetrievalQuery("为什么选方案B")))

    assert result.primary_domains == [MemoryDomain.PROJECT_DECISION]
    assert result.secondary_domains == [MemoryDomain.TEAM_RETENTION]
    assert result.intent_type == "project_decision"
    assert result.keywords == ["为什么", "方案"]
    assert result.confidence == 0.8


def test_retrieval_tracer_persists_trace_dict_and_keeps_recent_copy() -> None:
    persisted: list[dict[str, object]] = []
    tracer = RetrievalTracer(persist_fn=persisted.append)

    with tracer.start_trace("query-1") as ctx:
        ctx.set_metadata("mode", "test")
        with ctx.step("intent") as step:
            step.set_input({"query": "方案B"})
            step.set_output({"domain": "project_decision"})
        ctx.set_result_count(1)

    recent = tracer.recent_traces

    assert len(persisted) == 1
    assert persisted[0]["query_id"] == "query-1"
    assert persisted[0]["final_result_count"] == 1
    assert persisted[0]["metadata"] == {"mode": "test"}
    assert tracer.get_trace("query-1") is not None
    recent.clear()
    assert tracer.get_trace("query-1") is not None


def test_memory_item_from_core_accepts_schema_object() -> None:
    memory = MemoryCore(
        memory_id="memory-1",
        domain="project_decision",
        memory_type="decision",
        scope="project",
        source_type="feishu_chat",
        source_ref="event-1",
        content_text="团队决定使用方案B",
        summary_text="方案B 决策",
        entities=["方案B"],
        tags=["decision"],
        importance=0.8,
        confidence=0.9,
        embedding_id="embedding-1",
    )

    item = memory_item_from_core(memory, extra={"project_id": "project-1"})

    assert item.memory_id == "memory-1"
    assert item.domain == MemoryDomain.PROJECT_DECISION
    assert item.scope == MemoryScope.PROJECT
    assert item.entities == ["方案B"]
    assert item.tags == ["decision"]
    assert item.extra["source_type"] == "feishu_chat"
    assert item.extra["embedding_id"] == "embedding-1"
    assert item.extra["project_id"] == "project-1"


def test_memory_item_from_core_accepts_store_row_dict() -> None:
    row = {
        "memory_id": "memory-2",
        "domain": "team_retention",
        "memory_type": "team_fact",
        "scope": "team",
        "source_type": "feishu_chat",
        "source_ref": "event-2",
        "content_text": "客户要求上线前完成安全复核",
        "entities_json": ["客户", "安全复核"],
        "tags_json": ["risk"],
        "importance": 0.7,
        "confidence": 0.8,
        "status": "active",
        "created_at": "2026-04-27T00:00:00Z",
        "updated_at": "2026-04-27T00:00:00Z",
        "team_id": "team-1",
    }

    item = memory_item_from_core(row)

    assert item.domain == MemoryDomain.TEAM_RETENTION
    assert item.scope == MemoryScope.TEAM
    assert item.entities == ["客户", "安全复核"]
    assert item.tags == ["risk"]
    assert item.extra["team_id"] == "team-1"
