from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.retrieval import MemoryItem, RankedMemory, RetrievalQuery, memory_item_from_core
from src.llm import EmbeddingClient
from src.storage import EmbeddingStore, MemoryCoreStore, TeamRetentionStore
from src.utils.text import clean_text

from .models import TeamRetentionMemory
from .ranker import TeamRetentionRanker


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TeamRetentionQuery:
    query_text: str
    team_id: str | None = None
    project_id: str | None = None
    workspace_id: str | None = None
    fact_type: str | None = None
    risk_level: str | None = None
    include_superseded: bool = False
    limit: int = 10
    timestamp: str | None = None
    query_variants: list[str] = field(default_factory=list)

    @classmethod
    def from_retrieval_query(cls, query: RetrievalQuery, *, limit: int = 10) -> TeamRetentionQuery:
        session = query.session_context
        query_variants = session.get("query_variants")
        return cls(
            query_text=query.query_text,
            team_id=query.team_id or session.get("team_id"),
            project_id=query.project_id or session.get("project_id"),
            workspace_id=query.workspace_id or session.get("workspace_id"),
            fact_type=session.get("fact_type"),
            risk_level=session.get("risk_level"),
            limit=limit,
            timestamp=query.timestamp,
            query_variants=[
                variant
                for variant in (query_variants if isinstance(query_variants, list) else [query.query_text])
                if isinstance(variant, str) and variant.strip()
            ],
        )


@dataclass(slots=True)
class TeamRetentionRecallHit:
    memory_id: str
    source: str
    rank: int
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TeamRetentionSearchResult:
    memory: TeamRetentionMemory
    memory_item: MemoryItem
    score: float = 0.0
    match_reason: str = ""
    matched_fields: list[str] = field(default_factory=list)

    def to_ranked_memory(self, rank: int = 0) -> RankedMemory:
        self.memory_item.extra["team_retention_card"] = self.memory.to_card()
        self.memory_item.extra["matched_fields"] = list(self.matched_fields)
        return RankedMemory(
            item=self.memory_item,
            final_score=self.score,
            score_breakdown={"domain_score": self.score},
            rank=rank,
        )


class TeamRetentionRetriever:
    def __init__(
        self,
        memory_store: MemoryCoreStore,
        team_retention_store: TeamRetentionStore,
        *,
        embedding_store: EmbeddingStore | None = None,
        embedding_client: EmbeddingClient | None = None,
        ranker: TeamRetentionRanker | None = None,
        decay_rate: float = 0.001,
    ) -> None:
        self.memory_store = memory_store
        self.team_retention_store = team_retention_store
        self.embedding_store = embedding_store
        self.embedding_client = embedding_client
        self.ranker = ranker or TeamRetentionRanker()
        self.decay_rate = decay_rate

    def retrieve(
        self,
        query: TeamRetentionQuery | RetrievalQuery,
        *,
        limit: int | None = None,
    ) -> list[TeamRetentionSearchResult]:
        effective_limit = limit if limit is not None else (query.limit if isinstance(query, TeamRetentionQuery) else 10)
        if effective_limit < 1:
            raise ValueError("limit must be greater than 0")
        domain_query = self._coerce_query(query, limit=effective_limit)
        logger.info(
            "action=domain_retrieve_start domain=team_retention limit=%s variants=%s",
            effective_limit,
            len(domain_query.query_variants or []),
        )
        candidate_limit = max(effective_limit * 5, 30)
        variants = domain_query.query_variants or [domain_query.query_text]
        filters: dict[str, Any] = {}
        if domain_query.team_id:
            filters["team_id"] = domain_query.team_id
        if domain_query.project_id:
            filters["project_id"] = domain_query.project_id
        if domain_query.workspace_id:
            filters["workspace_id"] = domain_query.workspace_id
        if domain_query.fact_type:
            filters["fact_type"] = domain_query.fact_type

        all_recall_lists: list[list[TeamRetentionRecallHit]] = []
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
            table = self._table_overlap_recall(
                domain_query,
                variant,
                limit=candidate_limit,
                weight=weight,
            )
            for hits in (bm25, vec, table):
                if hits:
                    all_recall_lists.append(hits)

        if not all_recall_lists:
            candidate_rows = self.memory_store.search_memory_candidates(
                domain="team_retention",
                status="candidate",
                limit=max(effective_limit * 3, 20),
            )
            if not candidate_rows:
                return []
            filtered = self._filter_candidates(candidate_rows, domain_query)
            if not filtered:
                return []
            results = self._build_results(filtered, {})
            return self.ranker.rank(results, domain_query, limit=effective_limit)

        fused_hits = self._rrf_fuse(all_recall_lists, limit=candidate_limit)
        if not fused_hits:
            return []

        hit_by_id = {hit.memory_id: hit for hit in fused_hits}
        rows = self.memory_store.batch_get_memories([hit.memory_id for hit in fused_hits])

        if domain_query.include_superseded or True:
            candidate_rows = self.memory_store.search_memory_candidates(
                domain="team_retention",
                status="candidate",
                limit=max(effective_limit * 3, 20),
            )
            row_map = {row["memory_id"]: row for row in rows}
            for row in candidate_rows:
                if row["memory_id"] not in row_map:
                    row_map[row["memory_id"]] = row
            rows = list(row_map.values())

        filtered = self._filter_candidates(rows, domain_query)
        results = self._build_results(filtered, hit_by_id)
        results = self._apply_time_decay(results)
        return self.ranker.rank(results, domain_query, limit=effective_limit)

    # ------------------------------------------------------------------
    # BM25 recall
    # ------------------------------------------------------------------

    def _bm25_recall(
        self,
        query_text: str,
        *,
        limit: int,
        weight: float = 1.0,
        include_superseded: bool = False,
    ) -> list[TeamRetentionRecallHit]:
        try:
            rows = self.memory_store.search_bm25(
                query_text,
                domain="team_retention",
                status=None if include_superseded else "active",
                limit=limit,
            )
        except Exception:
            logger.warning(
                "action=bm25_recall_failed domain=team_retention query_text=%s",
                query_text,
                exc_info=True,
            )
            return []
        hits: list[TeamRetentionRecallHit] = []
        for rank, row in enumerate(rows, start=1):
            memory_id = row.get("memory_id")
            score = row.get("bm25_score")
            if not isinstance(memory_id, str) or not isinstance(score, (int, float)):
                continue
            hits.append(
                TeamRetentionRecallHit(
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

    # ------------------------------------------------------------------
    # Vector recall
    # ------------------------------------------------------------------

    def _vector_recall(
        self,
        query_text: str,
        *,
        limit: int,
        weight: float = 1.0,
        filters: dict[str, Any] | None = None,
    ) -> list[TeamRetentionRecallHit]:
        if self.embedding_store is None:
            return []
        try:
            if self.embedding_client is not None:
                hits = self.embedding_store.query_by_embedding(
                    self.embedding_client.embed_text(query_text),
                    domain="team_retention",
                    top_k=limit,
                    filters=filters,
                )
            else:
                hits = self.embedding_store.query_similar(
                    query_text,
                    domain="team_retention",
                    top_k=limit,
                    filters=filters,
                )
        except Exception:
            logger.warning(
                "action=vector_recall_failed domain=team_retention query_text=%s",
                query_text,
                exc_info=True,
            )
            return []
        result: list[TeamRetentionRecallHit] = []
        for rank, hit in enumerate(hits, start=1):
            memory_id = hit.get("memory_id") or hit.get("id")
            if not isinstance(memory_id, str):
                continue
            distance = hit.get("distance")
            similarity = 0.0
            if isinstance(distance, (int, float)):
                similarity = max(0.0, min(1.0, 1.0 - float(distance)))
            result.append(
                TeamRetentionRecallHit(
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

    # ------------------------------------------------------------------
    # Table lexical recall
    # ------------------------------------------------------------------

    def _table_overlap_recall(
        self,
        query: TeamRetentionQuery,
        query_text: str,
        *,
        limit: int,
        weight: float = 1.0,
    ) -> list[TeamRetentionRecallHit]:
        rows = self.memory_store.search_memory_candidates(
            domain="team_retention",
            status="active",
            limit=max(limit * 3, 100),
        )
        filtered = self._filter_candidates(rows, query)
        scored: list[tuple[float, str]] = []
        for row in filtered:
            text = " ".join(
                str(row.get(field) or "")
                for field in ("summary_text", "content_text")
            )
            score = _lexical_overlap_score(query_text, text)
            if score < 0.18:
                continue
            scored.append((score, str(row["memory_id"])))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [
            TeamRetentionRecallHit(
                memory_id=memory_id,
                source="table_overlap",
                rank=rank,
                score=score,
                metadata={
                    "table_overlap_score": score,
                    "matched_fields": ["table_overlap"],
                    "variant_weight": weight,
                },
            )
            for rank, (score, memory_id) in enumerate(scored[:limit], start=1)
        ]

    # ------------------------------------------------------------------
    # RRF fusion
    # ------------------------------------------------------------------

    def _rrf_fuse(
        self,
        ranked_lists: list[list[TeamRetentionRecallHit]],
        *,
        limit: int,
        k: int = 60,
    ) -> list[TeamRetentionRecallHit]:
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
        fused: list[TeamRetentionRecallHit] = []
        for rank, (memory_id, raw_score) in enumerate(ordered[:limit], start=1):
            metadata = metadata_by_id.get(memory_id, {})
            normalized_score = raw_score / max_score if max_score > 0 else raw_score
            metadata["rrf_raw_score"] = raw_score
            metadata["rrf_score"] = normalized_score
            fused.append(
                TeamRetentionRecallHit(
                    memory_id=memory_id,
                    source="rrf",
                    rank=rank,
                    score=normalized_score,
                    metadata=metadata,
                )
            )
        return fused

    # ------------------------------------------------------------------
    # Candidate filtering
    # ------------------------------------------------------------------

    def _filter_candidates(
        self,
        rows: list[dict[str, Any]],
        query: TeamRetentionQuery,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for row in rows:
            if not query.include_superseded and row.get("status") == "superseded":
                continue
            entities = list(row.get("entities") or row.get("entities_json") or [])
            if query.team_id and not self._entity_contains(entities, "team_id", query.team_id):
                continue
            if query.project_id and not self._entity_contains(entities, "project_id", query.project_id):
                continue
            if query.workspace_id and not self._entity_contains(entities, "workspace_id", query.workspace_id):
                continue
            if query.fact_type or query.risk_level:
                memory = self.team_retention_store.get_memory(row["memory_id"]) or TeamRetentionMemory.from_memory_core(row)
                if query.fact_type and query.fact_type != memory.fact_type:
                    continue
                if query.risk_level and query.risk_level != memory.risk_level:
                    continue
            result.append(row)
        return result

    # ------------------------------------------------------------------
    # Result building
    # ------------------------------------------------------------------

    def _build_results(
        self,
        rows: list[dict[str, Any]],
        hit_by_id: dict[str, TeamRetentionRecallHit],
    ) -> list[TeamRetentionSearchResult]:
        results: list[TeamRetentionSearchResult] = []
        for row in rows:
            hit = hit_by_id.get(row["memory_id"])
            memory = self.team_retention_store.get_memory(row["memory_id"]) or TeamRetentionMemory.from_memory_core(row)
            metadata = hit.metadata if hit is not None else {}
            score = hit.score if hit is not None else 0.15
            item = memory_item_from_core(
                row,
                extra={
                    "team_id": memory.team_id,
                    "project_id": memory.project_id,
                    "workspace_id": memory.workspace_id,
                    "fact_type": memory.fact_type,
                    "risk_level": memory.risk_level,
                    "next_review_at": memory.next_review_at,
                    "status": row.get("status"),
                    "needs_confirmation": memory.metadata.get("needs_confirmation", row.get("status") == "candidate"),
                    "recall_sources": list(metadata.get("recall_sources", [])),
                    "rrf_score": metadata.get("rrf_score", score),
                    "rrf_raw_score": metadata.get("rrf_raw_score"),
                },
            )
            for key in ("bm25_score", "vector_similarity", "vector_query"):
                if key in metadata:
                    item.extra[key] = metadata[key]
            if "table_overlap_score" in metadata:
                item.extra["table_overlap_score"] = metadata["table_overlap_score"]
            match_reason = "、".join(metadata.get("matched_fields", [])) if metadata.get("matched_fields") else ("rrf" if hit is not None else "candidate_pool")
            matched_fields = list(metadata.get("matched_fields", [])) if hit is not None else ["candidate_pool"]
            results.append(
                TeamRetentionSearchResult(
                    memory=memory,
                    memory_item=item,
                    score=score,
                    match_reason=match_reason,
                    matched_fields=matched_fields,
                )
            )
        return sorted(results, key=lambda r: (r.score, r.memory.retention_id), reverse=True)

    # ------------------------------------------------------------------
    # Time decay
    # ------------------------------------------------------------------

    def _apply_time_decay(self, results: list[TeamRetentionSearchResult]) -> list[TeamRetentionSearchResult]:
        if self.decay_rate <= 0 or not results:
            return results
        now = datetime.now(timezone.utc).isoformat()
        for result in results:
            factor = _time_decay_factor(
                result.memory.updated_at or result.memory.created_at,
                self.decay_rate,
                now,
            )
            if factor is not None:
                result.score *= factor
                result.memory_item.extra["time_decay"] = round(factor, 4)
        results.sort(key=lambda r: r.score, reverse=True)
        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _coerce_query(self, query: TeamRetentionQuery | RetrievalQuery, *, limit: int = 10) -> TeamRetentionQuery:
        if isinstance(query, TeamRetentionQuery):
            return query
        return TeamRetentionQuery.from_retrieval_query(query, limit=limit)

    def _entity_contains(self, entities: list[str], prefix: str, value: str) -> bool:
        prefixed = f"{prefix}:{value}"
        for entity in entities:
            if entity == value or entity == prefixed:
                return True
        return False


def _time_decay_factor(timestamp: str | None, decay_rate: float, now_iso: str) -> float:
    if not timestamp or decay_rate <= 0:
        return 1.0
    try:
        ts_date = timestamp[:10]
        now_date = now_iso[:10]
        ts_dt = datetime.strptime(ts_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        now_dt = datetime.strptime(now_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        days = (now_dt - ts_dt).days
        if days < 1:
            return 1.0
        return math.exp(-decay_rate * days)
    except Exception:
        return 1.0


def _lexical_overlap_score(query_text: str, memory_text: str) -> float:
    """Score Chinese-friendly lexical overlap without relying on SQLite FTS tokenization."""
    query_terms = _overlap_terms(query_text)
    memory_terms = _overlap_terms(memory_text)
    if not query_terms or not memory_terms:
        return 0.0
    overlap = query_terms & memory_terms
    if not overlap:
        return 0.0
    return len(overlap) / len(query_terms)


def _overlap_terms(text: str) -> set[str]:
    cleaned = clean_text(text).lower()
    terms = set(re.findall(r"[a-z0-9][a-z0-9_\-]{1,}", cleaned))
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", cleaned):
        if len(chunk) <= 4:
            terms.add(chunk)
            continue
        for size in (2, 3, 4):
            terms.update(chunk[index:index + size] for index in range(0, len(chunk) - size + 1))
    return terms
