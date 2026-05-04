from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Any

from src.retrieval import MemoryItem, RankedMemory, RetrievalQuery, memory_item_from_core
from src.llm import EmbeddingClient
from src.storage import EmbeddingStore, MemoryCoreStore
from src.utils.text import clean_text

from .models import ProjectDecision
from .ranker import ProjectDecisionRanker


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


class ProjectDecisionRetriever:
    """Retrieves project decision memories from MemoryCoreStore."""

    def __init__(
        self,
        memory_store: MemoryCoreStore,
        *,
        embedding_store: EmbeddingStore | None = None,
        embedding_client: EmbeddingClient | None = None,
        ranker: ProjectDecisionRanker | None = None,
    ) -> None:
        self.memory_store = memory_store
        self.embedding_store = embedding_store
        self.embedding_client = embedding_client
        self.ranker = ranker or ProjectDecisionRanker()

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
        bm25_hits = self._bm25_hits(domain_query, limit=effective_limit)
        vector_hits = self._vector_hits(domain_query, limit=effective_limit)
        rows = self._load_candidates(
            domain_query,
            limit=effective_limit,
            bm25_hits=bm25_hits,
            vector_hits=vector_hits,
        )
        filtered = self._filter_candidates(rows, domain_query)
        scored = self._score_matches(filtered, domain_query, bm25_hits=bm25_hits, vector_hits=vector_hits)
        return self.ranker.rank(scored, domain_query, limit=effective_limit)

    def retrieve_cards(
        self,
        query: ProjectDecisionQuery | RetrievalQuery,
        *,
        limit: int = 5,
        min_score: float = 0.55,
    ) -> list[dict[str, Any]]:
        results = self.retrieve(query, limit=limit)
        return [result.to_card() for result in results if result.score >= min_score]

    def _load_candidates(
        self,
        query: ProjectDecisionQuery,
        *,
        limit: int,
        bm25_hits: dict[str, float] | None = None,
        vector_hits: dict[str, tuple[float, str]] | None = None,
    ) -> list[dict[str, Any]]:
        row_map: dict[str, dict[str, Any]] = {}
        active_rows = self.memory_store.list_active_memories(
            domain="project_decision",
            limit=max(limit * 5, 50),
        )
        for row in active_rows:
            row_map[row["memory_id"]] = row
        if query.include_superseded:
            superseded_rows = self.memory_store.search_memory_candidates(
                domain="project_decision",
                status="superseded",
                limit=max(limit * 5, 50),
            )
            for row in superseded_rows:
                row_map[row["memory_id"]] = row
        for memory_id in bm25_hits or {}:
            row = self.memory_store.get_memory(memory_id)
            if row is None or row.get("domain") != "project_decision":
                continue
            if row.get("status") == "superseded" and not query.include_superseded:
                continue
            row_map[row["memory_id"]] = row
        for memory_id in vector_hits or {}:
            row = self.memory_store.get_memory(memory_id)
            if row is None or row.get("domain") != "project_decision":
                continue
            if row.get("status") == "superseded" and not query.include_superseded:
                continue
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

    def _score_matches(
        self,
        rows: list[dict[str, Any]],
        query: ProjectDecisionQuery,
        *,
        bm25_hits: dict[str, float] | None = None,
        vector_hits: dict[str, tuple[float, str]] | None = None,
    ) -> list[ProjectDecisionSearchResult]:
        terms = self._extract_query_terms(query.query_text)
        results: list[ProjectDecisionSearchResult] = []
        for row in rows:
            decision = ProjectDecision.from_memory_core(row)
            item = memory_item_from_core(
                row,
                extra={
                    "project_id": decision.project_id,
                    "workspace_id": decision.workspace_id,
                    "team_id": decision.team_id,
                    "topic": decision.topic,
                    "stage": decision.stage,
                },
            )
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
            bm25_score = (bm25_hits or {}).get(decision.decision_id)
            if bm25_score is not None:
                score += min(max(bm25_score, 0.0), 1.0) * 0.3
                matched_fields.append("bm25")
                item.extra["bm25_score"] = bm25_score
            vector_hit = (vector_hits or {}).get(decision.decision_id)
            if vector_hit is not None:
                vector_similarity, vector_query = vector_hit
                score += min(max(vector_similarity, 0.0), 1.0) * 0.35
                matched_fields.append("vector_similarity")
                item.extra["vector_similarity"] = vector_similarity
                item.extra["vector_query"] = vector_query
            score += min(decision.confidence, 1.0) * 0.05
            score += min(decision.importance, 1.0) * 0.05
            match_reason = "、".join(matched_fields) if matched_fields else "domain_fallback"
            results.append(
                ProjectDecisionSearchResult(
                    decision=decision,
                    memory_item=item,
                    score=min(score, 1.0),
                    match_reason=match_reason,
                    matched_fields=matched_fields,
                )
            )
        return results

    def _bm25_hits(self, query: ProjectDecisionQuery, *, limit: int) -> dict[str, float]:
        """使用 MemoryCore FTS5 BM25 索引补充关键词召回，失败时返回空结果。"""
        try:
            rows = self.memory_store.search_bm25(
                query.query_text,
                domain="project_decision",
                status=None if query.include_superseded else "active",
                limit=max(limit * 3, 10),
            )
        except Exception:
            logger.warning(
                "action=bm25_recall_failed domain=project_decision query_text=%s",
                query.query_text,
                exc_info=True,
            )
            return {}
        result: dict[str, float] = {}
        for row in rows:
            memory_id = row.get("memory_id")
            score = row.get("bm25_score")
            if isinstance(memory_id, str) and isinstance(score, (int, float)):
                result[memory_id] = max(result.get(memory_id, 0.0), float(score))
        return result

    def _vector_hits(self, query: ProjectDecisionQuery, *, limit: int) -> dict[str, tuple[float, str]]:
        """使用向量索引补充 project_decision 召回，失败时返回空结果。"""
        if self.embedding_store is None:
            return {}
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
                        top_k=max(limit * 3, 10),
                        filters=filters or None,
                    )
                else:
                    hits = self.embedding_store.query_similar(
                        variant,
                        domain="project_decision",
                        top_k=max(limit * 3, 10),
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
        return result

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
