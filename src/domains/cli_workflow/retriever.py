from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.retrieval import MemoryItem, RankedMemory, RetrievalQuery, memory_item_from_core
from src.storage import MemoryCoreStore
from src.utils.text import clean_text

from .models import CLIWorkflowMemory


@dataclass(slots=True)
class CLIWorkflowSearchResult:
    memory: CLIWorkflowMemory
    memory_item: MemoryItem
    score: float = 0.0
    match_reason: str = ""
    matched_fields: list[str] = field(default_factory=list)

    def to_ranked_memory(self, rank: int = 0) -> RankedMemory:
        self.memory_item.extra["workflow"] = self.memory.to_dict()
        self.memory_item.extra["matched_fields"] = list(self.matched_fields)
        return RankedMemory(
            item=self.memory_item,
            final_score=self.score,
            score_breakdown={"domain_score": self.score},
            rank=rank,
        )

    def to_suggestion(self) -> dict[str, Any]:
        return {
            "command_name": self.memory.command_name,
            "command_template": self.memory.command_template,
            "command_category": self.memory.command_category,
            "project_id": self.memory.project_id,
            "parameter_bindings": [
                {"param_name": pb.param_name, "param_value": pb.param_value, "frequency": pb.frequency}
                for pb in sorted(self.memory.parameter_bindings, key=lambda x: -x.frequency)
            ],
            "execution_count": self.memory.execution_count,
            "last_executed_at": self.memory.last_executed_at,
            "success_rate": self.memory.success_rate,
            "source_type": self.memory.source_type,
            "score": self.score,
        }

    def to_completion(self) -> list[str]:
        """输出补全候选列表。根据 matched_fields 决定补全内容。"""
        candidates: list[str] = []
        for pb in sorted(self.memory.parameter_bindings, key=lambda x: -x.frequency):
            candidates.append(f"--{pb.param_name} {pb.param_value}")
        return candidates


class CLIWorkflowRetriever:

    def __init__(self, memory_store: MemoryCoreStore) -> None:
        self.memory_store = memory_store

    def retrieve(
        self,
        query: RetrievalQuery,
        *,
        limit: int = 10,
    ) -> list[CLIWorkflowSearchResult]:
        if limit < 1:
            raise ValueError("limit must be greater than 0")

        rows = self._load_candidates(limit=limit)
        filtered = self._filter_candidates(rows, query)
        scored = self._score_matches(filtered, query)
        scored.sort(key=lambda r: -r.score)
        return scored[:limit]

    def _load_candidates(self, *, limit: int) -> list[dict[str, Any]]:
        active_rows = self.memory_store.search_memory_candidates(
            domain="cli_workflow",
            status="active",
            limit=max(limit * 10, 100),
        )
        return active_rows

    def _filter_candidates(
        self,
        rows: list[dict[str, Any]],
        query: RetrievalQuery,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for row in rows:
            if row.get("status") == "superseded":
                continue
            entities = list(row.get("entities") or row.get("entities_json") or [])
            row_user = self._entity_value(entities, "user_id")
            row_project = self._entity_value(entities, "project_id")

            # 必须匹配 user_id（个人记忆）
            if query.user_id and row_user and query.user_id != row_user:
                continue

            # 如果 query 指定了 project_id，优先匹配
            if query.project_id and row_project and query.project_id != row_project:
                continue

            result.append(row)
        return result

    def _score_matches(
        self,
        rows: list[dict[str, Any]],
        query: RetrievalQuery,
    ) -> list[CLIWorkflowSearchResult]:
        terms = self._extract_query_terms(query.query_text)
        results: list[CLIWorkflowSearchResult] = []
        query_lower = clean_text(query.query_text).lower()

        for row in rows:
            memory = CLIWorkflowMemory.from_memory_core(row)
            item = memory_item_from_core(row)
            search_text = self._row_search_text(row).lower()
            matched_fields: list[str] = []
            score = 0.0

            # 命令名精确匹配
            if query_lower and memory.command_name.lower() in query_lower:
                score += 0.25
                matched_fields.append("command_name_exact")
            elif query_lower and any(
                word in memory.command_name.lower()
                for word in query_lower.split()
            ):
                score += 0.15
                matched_fields.append("command_name_partial")

            # 项目匹配
            if query.project_id and query.project_id == memory.project_id:
                score += 0.15
                matched_fields.append("project_id")

            # user 匹配
            if query.user_id and query.user_id == memory.user_id:
                score += 0.10
                matched_fields.append("user_id")

            # 关键词匹配
            if terms and any(term.lower() in search_text for term in terms):
                score += 0.15
                matched_fields.append("keyword")

            # 参数名匹配（查询中包含参数名）
            if query_lower:
                for pb in memory.parameter_bindings:
                    if f"--{pb.param_name}" in query_lower or f"-{pb.param_name}" in query_lower:
                        score += 0.05
                        matched_fields.append(f"param:{pb.param_name}")
                        break

            # 频率分
            importance = float(row.get("importance") or 0.0)
            score += min(importance, 0.3) * 0.5

            # 新鲜度分
            freshness = float(row.get("freshness_score") or 0.0)
            score += min(freshness, 0.2) * 0.25

            # 置信度（成功率）
            confidence = float(row.get("confidence") or 0.0)
            score += min(confidence, 0.2) * 0.25

            # 同项目下的记忆加分
            if memory.project_id and query.project_id and memory.project_id == query.project_id:
                score += 0.05
                matched_fields.append("same_project")

            match_reason = "、".join(matched_fields) if matched_fields else "domain_fallback"
            results.append(
                CLIWorkflowSearchResult(
                    memory=memory,
                    memory_item=item,
                    score=min(score, 1.0),
                    match_reason=match_reason,
                    matched_fields=matched_fields,
                )
            )
        return results

    def _extract_query_terms(self, query_text: str) -> list[str]:
        cleaned = clean_text(query_text)
        raw_terms = re.findall(r"[一-鿿]{2,}|[A-Za-z0-9_\-]{2,}", cleaned)
        stop_words = {"我们", "之前", "这个", "那个", "一下", "为什么", "帮我", "怎么"}
        result: list[str] = []
        for term in raw_terms:
            if term in stop_words or term.lower() in stop_words:
                continue
            if term not in result:
                result.append(term)
        return result

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

    @staticmethod
    def _entity_value(entities: list[str], prefix: str) -> str | None:
        marker = f"{prefix}:"
        for entity in entities:
            if entity.startswith(marker):
                return entity[len(marker):]
        return None
