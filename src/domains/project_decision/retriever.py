from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Any

from src.retrieval import MemoryItem, RankedMemory, RetrievalQuery, memory_item_from_core
from src.llm import EmbeddingClient, RerankClient
from src.llm.rerank_base import RerankDocument
from src.storage import EmbeddingStore, MemoryCoreStore
from src.utils.text import clean_text

from .models import ProjectDecision


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ProjectDecisionQuery:
    query_text: str
    project_id: str | None = None
    workspace_id: str | None = None
    team_id: str | None = None
    topic: str | None = None
    stage: str | None = None
    time_window_start: str | None = None
    time_window_end: str | None = None
    limit: int = 10
    include_superseded: bool = False
    timestamp: str | None = None
    query_variants: list[str] = field(default_factory=list)

    @classmethod
    def from_retrieval_query(cls, query: RetrievalQuery, *, limit: int = 10) -> ProjectDecisionQuery:
        session = query.session_context
        time_window = session.get("time_window")
        time_window_start = None
        time_window_end = None
        if isinstance(time_window, dict):
            time_window_start = time_window.get("start")
            time_window_end = time_window.get("end")
        query_variants = session.get("query_variants")
        return cls(
            query_text=query.query_text,
            project_id=query.project_id or session.get("project_id"),
            workspace_id=query.workspace_id or session.get("workspace_id"),
            team_id=query.team_id or session.get("team_id"),
            topic=session.get("topic"),
            stage=session.get("stage"),
            time_window_start=time_window_start,
            time_window_end=time_window_end,
            limit=limit,
            timestamp=query.timestamp,
            query_variants=[
                variant
                for variant in (query_variants if isinstance(query_variants, list) else [query.query_text])
                if isinstance(variant, str) and variant.strip()
            ],
        )


@dataclass(slots=True)
class ProjectDecisionSearchResult:
    decision: ProjectDecision
    memory_item: MemoryItem
    score: float = 0.0
    match_reason: str = ""
    matched_fields: list[str] = field(default_factory=list)

    def to_ranked_memory(self, rank: int = 0) -> RankedMemory:
        self.memory_item.extra["decision_card"] = self.decision.to_card()
        self.memory_item.extra["matched_fields"] = list(self.matched_fields)
        return RankedMemory(
            item=self.memory_item,
            final_score=self.score,
            score_breakdown={"domain_score": self.score},
            rank=rank,
        )

    def to_card(self) -> dict[str, Any]:
        card = self.decision.to_card()
        card.update(
            {
                "score": self.score,
                "match_reason": self.match_reason,
                "source_ref": self.decision.source_ref or self.memory_item.source_ref,
            }
        )
        return card

    @property
    def item(self) -> MemoryItem:
        return self.memory_item


@dataclass(slots=True)
class ProjectDecisionRecallHit:
    """单路召回命中，供 RRF 融合和 rerank 前候选构造使用。"""

    memory_id: str
    source: str
    rank: int
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class ProjectDecisionRetriever:
    """Retrieves project decision memories from MemoryCoreStore."""

    def __init__(
        self,
        memory_store: MemoryCoreStore,
        *,
        embedding_store: EmbeddingStore | None = None,
        embedding_client: EmbeddingClient | None = None,
        rerank_client: RerankClient | None = None,
    ) -> None:
        self.memory_store = memory_store
        self.embedding_store = embedding_store
        self.embedding_client = embedding_client
        self.rerank_client = rerank_client

    def retrieve(
        self,
        query: ProjectDecisionQuery | RetrievalQuery,
        *,
        limit: int | None = None,
    ) -> list[ProjectDecisionSearchResult]:
        effective_limit = limit if limit is not None else (query.limit if isinstance(query, ProjectDecisionQuery) else 10)
        if effective_limit < 1:
            raise ValueError("limit must be greater than 0")
        domain_query = self._coerce_query(query, limit=effective_limit)
        logger.info(
            "action=domain_retrieve_start domain=project_decision limit=%s",
            effective_limit,
        )
        candidate_limit = max(effective_limit * 5, 30)
        bm25_hits = self._bm25_recall(domain_query, limit=candidate_limit)
        vector_hits = self._vector_recall(domain_query, limit=candidate_limit)
        recall_lists = [hits for hits in (bm25_hits, vector_hits) if hits]
        if not recall_lists:
            rule_hits = self._rule_recall(domain_query, limit=candidate_limit)
            recall_lists = [rule_hits] if rule_hits else []
        fused_hits = self._rrf_fuse(recall_lists, limit=candidate_limit)
        if not fused_hits:
            return []
        hit_by_id = {hit.memory_id: hit for hit in fused_hits}
        rows = self.memory_store.batch_get_memories([hit.memory_id for hit in fused_hits])
        filtered = self._filter_candidates(rows, domain_query)
        results = self._build_results(filtered, hit_by_id)
        return self._rerank_results(domain_query, results, limit=effective_limit)

    def retrieve_cards(
        self,
        query: ProjectDecisionQuery | RetrievalQuery,
        *,
        limit: int = 5,
        min_score: float = 0.55,
    ) -> list[dict[str, Any]]:
        results = self.retrieve(query, limit=limit)
        return [result.to_card() for result in results if result.score >= min_score]

    def _rrf_fuse(
        self,
        ranked_lists: list[list[ProjectDecisionRecallHit]],
        *,
        limit: int,
        k: int = 60,
    ) -> list[ProjectDecisionRecallHit]:
        """使用 RRF 融合多路召回列表，并保留各路证据 metadata。"""
        if not ranked_lists:
            return []
        source_weights = {"bm25": 1.0, "vector": 1.0, "rule": 0.5}
        score_by_id: dict[str, float] = {}
        metadata_by_id: dict[str, dict[str, Any]] = {}
        for ranked_list in ranked_lists:
            for hit in ranked_list:
                source = hit.source
                score_by_id[hit.memory_id] = score_by_id.get(hit.memory_id, 0.0) + (
                    source_weights.get(source, 1.0) / (k + hit.rank)
                )
                metadata = metadata_by_id.setdefault(
                    hit.memory_id,
                    {"recall_sources": [], "matched_fields": []},
                )
                if source not in metadata["recall_sources"]:
                    metadata["recall_sources"].append(source)
                for field_name in hit.metadata.get("matched_fields", []):
                    if field_name not in metadata["matched_fields"]:
                        metadata["matched_fields"].append(field_name)
                for key, value in hit.metadata.items():
                    if key in {"matched_fields"}:
                        continue
                    if key == "recall_sources":
                        for item in value:
                            if item not in metadata["recall_sources"]:
                                metadata["recall_sources"].append(item)
                    elif key in {"bm25_score", "vector_similarity"}:
                        metadata[key] = max(float(metadata.get(key, 0.0)), float(value))
                    else:
                        metadata[key] = value
        ordered = sorted(score_by_id.items(), key=lambda item: (item[1], item[0]), reverse=True)
        max_score = ordered[0][1] if ordered else 1.0
        fused: list[ProjectDecisionRecallHit] = []
        for rank, (memory_id, raw_score) in enumerate(ordered[:limit], start=1):
            metadata = metadata_by_id.get(memory_id, {})
            normalized_score = raw_score / max_score if max_score > 0 else raw_score
            metadata["rrf_raw_score"] = raw_score
            metadata["rrf_score"] = normalized_score
            fused.append(
                ProjectDecisionRecallHit(
                    memory_id=memory_id,
                    source="rrf",
                    rank=rank,
                    score=normalized_score,
                    metadata=metadata,
                )
            )
        return fused

    def _build_results(
        self,
        rows: list[dict[str, Any]],
        hit_by_id: dict[str, ProjectDecisionRecallHit],
    ) -> list[ProjectDecisionSearchResult]:
        """将 RRF 命中和 MemoryCore 行组装为 ProjectDecisionSearchResult。"""
        results: list[ProjectDecisionSearchResult] = []
        for row in rows:
            hit = hit_by_id.get(row["memory_id"])
            if hit is None:
                continue
            decision = ProjectDecision.from_memory_core(row)
            metadata = hit.metadata
            item = memory_item_from_core(
                row,
                extra={
                    "project_id": decision.project_id,
                    "workspace_id": decision.workspace_id,
                    "team_id": decision.team_id,
                    "topic": decision.topic,
                    "stage": decision.stage,
                    "recall_sources": list(metadata.get("recall_sources", [])),
                    "rrf_score": metadata.get("rrf_score", hit.score),
                    "rrf_raw_score": metadata.get("rrf_raw_score"),
                },
            )
            for key in ("bm25_score", "vector_similarity", "vector_query"):
                if key in metadata:
                    item.extra[key] = metadata[key]
            matched_fields = list(metadata.get("matched_fields", []))
            results.append(
                ProjectDecisionSearchResult(
                    decision=decision,
                    memory_item=item,
                    score=hit.score,
                    match_reason="、".join(matched_fields) if matched_fields else "rrf",
                    matched_fields=matched_fields,
                )
            )
        return sorted(results, key=lambda result: (result.score, result.decision.decision_id), reverse=True)

    def _rerank_results(
        self,
        query: ProjectDecisionQuery,
        results: list[ProjectDecisionSearchResult],
        *,
        limit: int,
    ) -> list[ProjectDecisionSearchResult]:
        """使用可选 rerank 模型重排 RRF 候选，失败时回退 RRF 顺序。"""
        if self.rerank_client is None or len(results) <= 1:
            return results[:limit]
        documents = [
            RerankDocument(
                id=result.decision.decision_id,
                text=result.memory_item.summary_text or result.memory_item.content_text,
                metadata={
                    "domain": "project_decision",
                    "rrf_score": result.memory_item.extra.get("rrf_score", result.score),
                    "recall_sources": list(result.memory_item.extra.get("recall_sources", [])),
                },
            )
            for result in results
        ]
        try:
            response = self.rerank_client.rerank(query.query_text, documents, top_k=limit)
        except Exception:
            logger.warning(
                "action=project_decision_rerank_failed query_text=%s candidate_count=%s",
                query.query_text,
                len(results),
                exc_info=True,
            )
            return results[:limit]
        result_by_id = {result.decision.decision_id: result for result in results}
        reranked: list[ProjectDecisionSearchResult] = []
        for rerank_result in response.results:
            result = result_by_id.get(rerank_result.id)
            if result is None:
                continue
            result.score = float(rerank_result.score)
            result.memory_item.extra["rerank_score"] = float(rerank_result.score)
            result.memory_item.extra["rerank_model"] = response.model
            reranked.append(result)
        return reranked[:limit]

    def _bm25_recall(self, query: ProjectDecisionQuery, *, limit: int) -> list[ProjectDecisionRecallHit]:
        """使用 MemoryCore FTS5 BM25 索引返回有序关键词召回列表。"""
        try:
            rows = self.memory_store.search_bm25(
                query.query_text,
                domain="project_decision",
                status=None if query.include_superseded else "active",
                limit=limit,
            )
        except Exception:
            logger.warning(
                "action=bm25_recall_failed domain=project_decision query_text=%s",
                query.query_text,
                exc_info=True,
            )
            return []
        hits: list[ProjectDecisionRecallHit] = []
        for rank, row in enumerate(rows, start=1):
            memory_id = row.get("memory_id")
            score = row.get("bm25_score")
            if not isinstance(memory_id, str) or not isinstance(score, (int, float)):
                continue
            hits.append(
                ProjectDecisionRecallHit(
                    memory_id=memory_id,
                    source="bm25",
                    rank=rank,
                    score=float(score),
                    metadata={"bm25_score": float(score), "matched_fields": ["bm25"]},
                )
            )
        return hits

    def _vector_recall(self, query: ProjectDecisionQuery, *, limit: int) -> list[ProjectDecisionRecallHit]:
        """使用向量索引返回有序语义召回列表，单个 query variant 失败不阻断其他路。"""
        if self.embedding_store is None:
            return []
        filters: dict[str, Any] = {}
        if query.project_id:
            filters["project_id"] = query.project_id
        if query.team_id:
            filters["team_id"] = query.team_id
        if query.workspace_id:
            filters["workspace_id"] = query.workspace_id
        if query.stage:
            filters["stage"] = query.stage
        result: dict[str, tuple[float, str]] = {}
        variants = query.query_variants or [query.query_text]
        for variant in variants:
            try:
                if self.embedding_client is not None:
                    hits = self.embedding_store.query_by_embedding(
                        self.embedding_client.embed_text(variant),
                        domain="project_decision",
                        top_k=limit,
                        filters=filters or None,
                    )
                else:
                    hits = self.embedding_store.query_similar(
                        variant,
                        domain="project_decision",
                        top_k=limit,
                        filters=filters or None,
                    )
            except Exception:
                logger.warning(
                    "action=vector_recall_failed domain=project_decision query_text=%s",
                    variant,
                    exc_info=True,
                )
                continue
            for hit in hits:
                memory_id = hit.get("memory_id") or hit.get("id")
                if not isinstance(memory_id, str):
                    continue
                distance = hit.get("distance")
                similarity = 0.0
                if isinstance(distance, (int, float)):
                    similarity = max(0.0, min(1.0, 1.0 - float(distance)))
                old_similarity = result.get(memory_id, (0.0, ""))[0]
                if similarity >= old_similarity:
                    result[memory_id] = (similarity, variant)
        ordered = sorted(result.items(), key=lambda item: (item[1][0], item[0]), reverse=True)
        return [
            ProjectDecisionRecallHit(
                memory_id=memory_id,
                source="vector",
                rank=rank,
                score=similarity,
                metadata={
                    "vector_similarity": similarity,
                    "vector_query": variant,
                    "matched_fields": ["vector_similarity"],
                },
            )
            for rank, (memory_id, (similarity, variant)) in enumerate(ordered[:limit], start=1)
        ]

    def _rule_recall(self, query: ProjectDecisionQuery, *, limit: int) -> list[ProjectDecisionRecallHit]:
        """在 BM25 和向量均无命中时，使用原规则匹配作为 fallback 召回。"""
        rows = self._load_rule_candidates(query, limit=limit)
        filtered = self._filter_candidates(rows, query)
        hits: list[ProjectDecisionRecallHit] = []
        for row in filtered:
            rule_score, matched_fields = self._rule_score(row, query)
            hits.append(
                ProjectDecisionRecallHit(
                    memory_id=row["memory_id"],
                    source="rule",
                    rank=0,
                    score=rule_score,
                    metadata={"matched_fields": matched_fields or ["rule_fallback"]},
                )
            )
        hits.sort(key=lambda hit: (hit.score, hit.memory_id), reverse=True)
        for rank, hit in enumerate(hits[:limit], start=1):
            hit.rank = rank
        return hits[:limit]

    def _load_rule_candidates(self, query: ProjectDecisionQuery, *, limit: int) -> list[dict[str, Any]]:
        """加载规则 fallback 候选行，保持旧规则检索的 active/superseded 范围。"""
        row_map: dict[str, dict[str, Any]] = {}
        active_rows = self.memory_store.list_active_memories(
            domain="project_decision",
            limit=max(limit, 50),
        )
        for row in active_rows:
            row_map[row["memory_id"]] = row
        if query.include_superseded:
            superseded_rows = self.memory_store.search_memory_candidates(
                domain="project_decision",
                status="superseded",
                limit=max(limit, 50),
            )
            for row in superseded_rows:
                row_map[row["memory_id"]] = row
        return list(row_map.values())

    def _filter_candidates(
        self,
        rows: list[dict[str, Any]],
        query: ProjectDecisionQuery,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for row in rows:
            if not query.include_superseded and row.get("status") == "superseded":
                continue
            text = self._row_search_text(row)
            entities = list(row.get("entities") or row.get("entities_json") or [])
            tags = list(row.get("tags") or row.get("tags_json") or [])
            if query.project_id and not self._contains_any(text, entities + tags, query.project_id):
                continue
            if query.team_id and not self._contains_any(text, entities + tags, query.team_id):
                continue
            if query.workspace_id and not self._contains_any(text, entities + tags, query.workspace_id):
                continue
            if query.stage and query.stage.lower() not in text.lower():
                continue
            if query.topic and query.topic.lower() not in text.lower():
                continue
            result.append(row)
        return result

    def _rule_score(self, row: dict[str, Any], query: ProjectDecisionQuery) -> tuple[float, list[str]]:
        """计算规则 fallback 单条候选的匹配分和命中字段。"""
        terms = self._extract_query_terms(query.query_text)
        decision = ProjectDecision.from_memory_core(row)
        text = self._row_search_text(row).lower()
        matched_fields: list[str] = []
        score = 0.0
        if query.topic and query.topic.lower() in text:
            score += 0.35
            matched_fields.append("topic")
        if terms and any(term.lower() in text for term in terms):
            score += 0.25
            matched_fields.append("query_text")
        if query.project_id and query.project_id == decision.project_id:
            score += 0.2
            matched_fields.append("project_id")
        if query.stage and query.stage == decision.stage:
            score += 0.1
            matched_fields.append("stage")
        score += min(decision.confidence, 1.0) * 0.05
        score += min(decision.importance, 1.0) * 0.05
        return min(score, 1.0), matched_fields

    def _extract_query_terms(self, query_text: str) -> list[str]:
        cleaned = clean_text(query_text)
        raw_terms = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_\-]{2,}", cleaned)
        stop_words = {"我们", "之前", "这个", "那个", "一下", "为什么", "历史决策"}
        result: list[str] = []
        for term in raw_terms:
            if term in stop_words or term.lower() in stop_words:
                continue
            if term not in result:
                result.append(term)
        return result

    def _coerce_query(self, query: ProjectDecisionQuery | RetrievalQuery, *, limit: int = 10) -> ProjectDecisionQuery:
        if isinstance(query, ProjectDecisionQuery):
            return query
        return ProjectDecisionQuery.from_retrieval_query(query, limit=limit)

    def _row_search_text(self, row: dict[str, Any]) -> str:
        entities = " ".join(row.get("entities") or row.get("entities_json") or [])
        tags = " ".join(row.get("tags") or row.get("tags_json") or [])
        return " ".join(
            clean_text(part)
            for part in (
                row.get("summary_text"),
                row.get("content_text"),
                row.get("source_ref"),
                entities,
                tags,
            )
            if part
        )

    def _contains_any(self, text: str, fields: list[str], needle: str) -> bool:
        lowered = needle.lower()
        return lowered in text.lower() or any(lowered == field.lower() for field in fields)
