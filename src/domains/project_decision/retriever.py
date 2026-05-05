from __future__ import annotations

import math
import re
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
        decay_rate: float = 0.001,
    ) -> None:
        self.memory_store = memory_store
        self.embedding_store = embedding_store
        self.embedding_client = embedding_client
        self.rerank_client = rerank_client
        self.decay_rate = decay_rate

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
        variants = domain_query.query_variants or [domain_query.query_text]
        filters: dict[str, Any] = {}
        if domain_query.project_id:
            filters["project_id"] = domain_query.project_id
        if domain_query.team_id:
            filters["team_id"] = domain_query.team_id
        if domain_query.workspace_id:
            filters["workspace_id"] = domain_query.workspace_id
        if domain_query.stage:
            filters["stage"] = domain_query.stage

        all_recall_lists: list[list[ProjectDecisionRecallHit]] = []
        for i, variant in enumerate(variants):
            weight = 2.0 if i == 0 else 1.0
            bm25 = self._bm25_recall(
                variant,
                limit=candidate_limit,
                weight=weight,
                include_superseded=domain_query.include_superseded,
            )
            vec = self._vector_recall(
                variant,
                limit=candidate_limit,
                weight=weight,
                filters=filters or None,
            )
            for hits in (bm25, vec):
                if hits:
                    all_recall_lists.append(hits)

        if not all_recall_lists:
            rule_hits = self._rule_recall(domain_query, limit=candidate_limit)
            all_recall_lists = [rule_hits] if rule_hits else []
        fused_hits = self._rrf_fuse(all_recall_lists, limit=candidate_limit)
        if not fused_hits:
            return []
        hit_by_id = {hit.memory_id: hit for hit in fused_hits}
        rows = self.memory_store.batch_get_memories([hit.memory_id for hit in fused_hits])
        filtered = self._filter_candidates(rows, domain_query)
        results = self._build_results(filtered, hit_by_id)
        results = self._rerank_results(domain_query, results, limit=effective_limit)
        return self._apply_time_decay(results)

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
        """使用 RRF 融合多路召回列表，支持原始查询加权和 top-rank 加分。"""
        if not ranked_lists:
            return []
        score_by_id: dict[str, float] = {}
        metadata_by_id: dict[str, dict[str, Any]] = {}
        bonus_by_id: dict[str, set[str]] = {}
        for ranked_list in ranked_lists:
            for hit in ranked_list:
                source = hit.source
                variant_weight = float(hit.metadata.get("variant_weight", 1.0))
                score_by_id[hit.memory_id] = score_by_id.get(hit.memory_id, 0.0) + (
                    variant_weight / (k + hit.rank)
                )
                # Top-rank bonus: once per document, not per list
                if hit.rank == 1:
                    bonus_by_id.setdefault(hit.memory_id, set()).add("top")
                elif hit.rank in (2, 3):
                    bonus_by_id.setdefault(hit.memory_id, set()).add("high")
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
        for memory_id, tiers in bonus_by_id.items():
            if "top" in tiers:
                score_by_id[memory_id] = score_by_id.get(memory_id, 0.0) + 0.05
            elif "high" in tiers:
                score_by_id[memory_id] = score_by_id.get(memory_id, 0.0) + 0.02
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

    def _rrf_weight_for_rank(self, rank: int) -> float:
        """Position-aware RRF weight: top ranks trust RRF more, later ranks trust reranker more."""
        if rank <= 3:
            return 0.75
        if rank <= 10:
            return 0.60
        return 0.40

    def _apply_time_decay(self, results: list[ProjectDecisionSearchResult]) -> list[ProjectDecisionSearchResult]:
        """Apply exponential time decay so recent decisions score higher than old ones."""
        if self.decay_rate <= 0 or not results:
            return results
        now = datetime.now(timezone.utc).isoformat()
        for result in results:
            factor = _time_decay_factor(result.decision.decided_at, self.decay_rate, now)
            result.score *= factor
            result.memory_item.extra["time_decay"] = round(factor, 4)
        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def _build_rerank_text(self, decision: ProjectDecision) -> str:
        """Build structured text for reranker input, richer than raw summary_text."""
        parts: list[str] = []
        if decision.topic:
            parts.append(f"主题: {decision.topic}")
        conclusion = decision.conclusion or decision.decision
        if conclusion:
            parts.append(f"决策: {conclusion}")
        if decision.stage:
            parts.append(f"阶段: {decision.stage}")
        if decision.alternatives:
            parts.append(f"备选: {'; '.join(decision.alternatives[:3])}")
        if decision.reasons:
            parts.append(f"理由: {'; '.join(decision.reasons[:3])}")
        return "\n".join(parts) if parts else (conclusion or decision.topic or "")

    def _rerank_results(
        self,
        query: ProjectDecisionQuery,
        results: list[ProjectDecisionSearchResult],
        *,
        limit: int,
    ) -> list[ProjectDecisionSearchResult]:
        """使用可选 rerank 模型重排 RRF 候选，位置感知混合 RRF 与 rerank 分数。"""
        if self.rerank_client is None or len(results) <= 1:
            return results[:limit]
        documents = [
            RerankDocument(
                id=result.decision.decision_id,
                text=self._build_rerank_text(result.decision),
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
        rrf_rank_by_id = {
            result.decision.decision_id: rank + 1
            for rank, result in enumerate(results)
        }
        rerank_scores = [float(r.score) for r in response.results]
        rerank_min = min(rerank_scores) if rerank_scores else 0.0
        rerank_max = max(rerank_scores) if rerank_scores else 1.0
        rerank_range = rerank_max - rerank_min or 1.0

        reranked: list[ProjectDecisionSearchResult] = []
        for rerank_result in response.results:
            result = result_by_id.get(rerank_result.id)
            if result is None:
                continue
            rrf_score = float(result.memory_item.extra.get("rrf_score", result.score))
            raw_rerank = float(rerank_result.score)
            norm_rerank = (raw_rerank - rerank_min) / rerank_range
            rrf_rank = rrf_rank_by_id.get(result.decision.decision_id, len(results))
            rrf_weight = self._rrf_weight_for_rank(rrf_rank)
            blended = rrf_weight * rrf_score + (1.0 - rrf_weight) * norm_rerank
            result.score = blended
            result.memory_item.extra["rrf_score"] = rrf_score
            result.memory_item.extra["rrf_rank"] = rrf_rank
            result.memory_item.extra["rrf_weight"] = rrf_weight
            result.memory_item.extra["rerank_score"] = raw_rerank
            result.memory_item.extra["rerank_score_norm"] = norm_rerank
            result.memory_item.extra["rerank_model"] = response.model
            reranked.append(result)
        return sorted(reranked, key=lambda r: r.score, reverse=True)[:limit]

    def _bm25_recall(
        self,
        query_text: str,
        *,
        limit: int,
        weight: float = 1.0,
        include_superseded: bool = False,
    ) -> list[ProjectDecisionRecallHit]:
        """单查询 BM25 关键词召回，weight 用于区分原始查询与扩展查询。"""
        try:
            rows = self.memory_store.search_bm25(
                query_text,
                domain="project_decision",
                status=None if include_superseded else "active",
                limit=limit,
            )
        except Exception:
            logger.warning(
                "action=bm25_recall_failed domain=project_decision query_text=%s",
                query_text,
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
                    metadata={
                        "bm25_score": float(score),
                        "matched_fields": ["bm25"],
                        "variant_weight": weight,
                    },
                )
            )
        return hits

    def _vector_recall(
        self,
        query_text: str,
        *,
        limit: int,
        weight: float = 1.0,
        filters: dict[str, Any] | None = None,
    ) -> list[ProjectDecisionRecallHit]:
        """单查询向量语义召回，weight 用于区分原始查询与扩展查询。"""
        if self.embedding_store is None:
            return []
        try:
            if self.embedding_client is not None:
                hits = self.embedding_store.query_by_embedding(
                    self.embedding_client.embed_text(query_text),
                    domain="project_decision",
                    top_k=limit,
                    filters=filters,
                )
            else:
                hits = self.embedding_store.query_similar(
                    query_text,
                    domain="project_decision",
                    top_k=limit,
                    filters=filters,
                )
        except Exception:
            logger.warning(
                "action=vector_recall_failed domain=project_decision query_text=%s",
                query_text,
                exc_info=True,
            )
            return []
        result: list[ProjectDecisionRecallHit] = []
        for rank, hit in enumerate(hits, start=1):
            memory_id = hit.get("memory_id") or hit.get("id")
            if not isinstance(memory_id, str):
                continue
            distance = hit.get("distance")
            similarity = 0.0
            if isinstance(distance, (int, float)):
                similarity = max(0.0, min(1.0, 1.0 - float(distance)))
            result.append(
                ProjectDecisionRecallHit(
                    memory_id=memory_id,
                    source="vector",
                    rank=rank,
                    score=similarity,
                    metadata={
                        "vector_similarity": similarity,
                        "vector_query": query_text,
                        "matched_fields": ["vector_similarity"],
                        "variant_weight": weight,
                    },
                )
            )
        return result

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
            entities = list(row.get("entities") or row.get("entities_json") or [])
            tags = list(row.get("tags") or row.get("tags_json") or [])
            if query.project_id and not self._entity_contains(entities, "project_id", query.project_id):
                continue
            if query.team_id and not self._entity_contains(entities, "team_id", query.team_id):
                continue
            if query.workspace_id and not self._entity_contains(entities, "workspace_id", query.workspace_id):
                continue
            if query.stage or query.topic:
                text = self._row_search_text(row)
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

    def _entity_contains(self, entities: list[str], prefix: str, value: str) -> bool:
        """Check if entities list contains a prefixed entry (e.g. project_id:foo) or the raw value."""
        prefixed = f"{prefix}:{value}"
        for entity in entities:
            if entity == value or entity == prefixed:
                return True
        return False

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


def _time_decay_factor(decided_at: str | None, decay_rate: float, now_iso: str) -> float:
    """Exponential decay factor based on days since decision was made."""
    if not decided_at or decay_rate <= 0:
        return 1.0
    try:
        decided_date = decided_at[:10]
        now_date = now_iso[:10]
        decided_dt = datetime.strptime(decided_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        now_dt = datetime.strptime(now_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        days = (now_dt - decided_dt).days
        if days < 1:
            return 1.0
        return math.exp(-decay_rate * days)
    except Exception:
        return 1.0
