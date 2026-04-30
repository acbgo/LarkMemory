from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.retrieval import MemoryItem, RankedMemory, RetrievalQuery, memory_item_from_core
from src.storage import MemoryCoreStore, TeamRetentionStore
from src.utils.text import clean_text

from .models import TeamRetentionMemory
from .ranker import TeamRetentionRanker


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

    @classmethod
    def from_retrieval_query(cls, query: RetrievalQuery, *, limit: int = 10) -> TeamRetentionQuery:
        session = query.session_context
        return cls(
            query_text=query.query_text,
            team_id=query.team_id or session.get("team_id"),
            project_id=query.project_id or session.get("project_id"),
            workspace_id=query.workspace_id or session.get("workspace_id"),
            fact_type=session.get("fact_type"),
            risk_level=session.get("risk_level"),
            limit=limit,
            timestamp=query.timestamp,
        )


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
        ranker: TeamRetentionRanker | None = None,
    ) -> None:
        self.memory_store = memory_store
        self.team_retention_store = team_retention_store
        self.ranker = ranker or TeamRetentionRanker()

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
        if not (domain_query.team_id or domain_query.project_id or domain_query.workspace_id):
            return []
        rows = self._load_candidates(domain_query, limit=effective_limit)
        filtered = self._filter_candidates(rows, domain_query)
        scored = self._score_matches(filtered, domain_query)
        return self.ranker.rank(scored, domain_query, limit=effective_limit)

    def _load_candidates(self, query: TeamRetentionQuery, *, limit: int) -> list[dict[str, Any]]:
        row_map: dict[str, dict[str, Any]] = {}
        active_rows = self.memory_store.list_active_memories(
            domain="team_retention",
            limit=max(limit * 5, 50),
        )
        for row in active_rows:
            row_map[row["memory_id"]] = row
        candidate_rows = self.memory_store.search_memory_candidates(
            domain="team_retention",
            status="candidate",
            limit=max(limit * 5, 50),
        )
        for row in candidate_rows:
            row_map[row["memory_id"]] = row
        if query.include_superseded:
            superseded_rows = self.memory_store.search_memory_candidates(
                domain="team_retention",
                status="superseded",
                limit=max(limit * 5, 50),
            )
            for row in superseded_rows:
                row_map[row["memory_id"]] = row
        return list(row_map.values())

    def _filter_candidates(
        self,
        rows: list[dict[str, Any]],
        query: TeamRetentionQuery,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for row in rows:
            memory = self.team_retention_store.get_memory(row["memory_id"]) or TeamRetentionMemory.from_memory_core(row)
            if query.team_id and query.team_id != memory.team_id:
                continue
            if query.project_id and query.project_id != memory.project_id:
                continue
            if query.workspace_id and query.workspace_id != memory.workspace_id:
                continue
            if query.fact_type and query.fact_type != memory.fact_type:
                continue
            if query.risk_level and query.risk_level != memory.risk_level:
                continue
            result.append(row)
        return result

    def _score_matches(
        self,
        rows: list[dict[str, Any]],
        query: TeamRetentionQuery,
    ) -> list[TeamRetentionSearchResult]:
        terms = self._extract_query_terms(query.query_text)
        results: list[TeamRetentionSearchResult] = []
        for row in rows:
            memory = self.team_retention_store.get_memory(row["memory_id"]) or TeamRetentionMemory.from_memory_core(row)
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
                },
            )
            text = self._row_search_text(row, memory).lower()
            matched_fields: list[str] = []
            score = 0.0
            if terms:
                matched = [term for term in terms if term.lower() in text]
                if matched:
                    score += min(len(matched) / len(terms), 1.0) * 0.45
                    matched_fields.append("query_text")
            if query.fact_type and query.fact_type == memory.fact_type:
                score += 0.2
                matched_fields.append("fact_type")
            if query.team_id and query.team_id == memory.team_id:
                score += 0.15
                matched_fields.append("team_id")
            if query.project_id and query.project_id == memory.project_id:
                score += 0.1
                matched_fields.append("project_id")
            if memory.risk_level == "high":
                score += 0.1
                matched_fields.append("risk_level")
            results.append(
                TeamRetentionSearchResult(
                    memory=memory,
                    memory_item=item,
                    score=min(score, 1.0),
                    match_reason=", ".join(matched_fields) if matched_fields else "domain_fallback",
                    matched_fields=matched_fields,
                )
            )
        return results

    def _coerce_query(self, query: TeamRetentionQuery | RetrievalQuery, *, limit: int = 10) -> TeamRetentionQuery:
        if isinstance(query, TeamRetentionQuery):
            return query
        return TeamRetentionQuery.from_retrieval_query(query, limit=limit)

    def _row_search_text(self, row: dict[str, Any], memory: TeamRetentionMemory) -> str:
        entities = " ".join(row.get("entities") or row.get("entities_json") or [])
        tags = " ".join(row.get("tags") or row.get("tags_json") or [])
        return " ".join(
            clean_text(part)
            for part in (
                row.get("summary_text"),
                row.get("content_text"),
                row.get("source_ref"),
                memory.fact_type,
                memory.fact_value,
                memory.owner,
                entities,
                tags,
            )
            if part
        )

    def _extract_query_terms(self, query_text: str) -> list[str]:
        raw_terms = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_\-]{2,}", clean_text(query_text))
        stop_words = {"team", "memory", "review", "remind", "what", "about"}
        result: list[str] = []
        for term in raw_terms:
            if term.lower() in stop_words:
                continue
            if term not in result:
                result.append(term)
        return result
