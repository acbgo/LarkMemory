from __future__ import annotations

from typing import Any

from src.core.domain_handler import DomainIngestResult, DomainRuntime, DomainUpdateResult
from src.retrieval import RankedMemory, RetrievalQuery
from src.schemas import NormalizedEvent
from src.storage import MemoryCoreStore, TeamRetentionStore
from src.utils.ids import new_id

from .extractor import TeamRetentionExtractor
from .models import TeamRetentionMemory
from .retriever import TeamRetentionRetriever
from .versioning import TeamRetentionVersionManager


class TeamRetentionDomainHandler:
    domain = "team_retention"

    def __init__(
        self,
        memory_store: MemoryCoreStore,
        team_retention_store: TeamRetentionStore,
        *,
        llm_client: Any | None = None,
        extractor: TeamRetentionExtractor | None = None,
        retriever: TeamRetentionRetriever | None = None,
        version_manager: TeamRetentionVersionManager | None = None,
    ) -> None:
        self.memory_store = memory_store
        self.team_retention_store = team_retention_store
        self.extractor = extractor or TeamRetentionExtractor(llm_client=llm_client)
        self.retriever = retriever or TeamRetentionRetriever(memory_store, team_retention_store)
        self.version_manager = version_manager or TeamRetentionVersionManager(memory_store, team_retention_store)

    def ingest_event(self, event: NormalizedEvent, runtime: DomainRuntime) -> DomainIngestResult:
        candidates = self.extractor.extract(event)
        memory_ids: list[str] = []
        for candidate in candidates:
            duplicate_id = self._find_duplicate(candidate.memory)
            if duplicate_id is not None:
                memory_ids.append(duplicate_id)
                self.team_retention_store.reinforce_review(duplicate_id, observed_at=event.occurred_at)
                continue
            version_decision = self.version_manager.detect_update(candidate.memory)
            if version_decision.should_supersede and version_decision.old_memory_id:
                candidate.memory.overwrite_of = version_decision.old_memory_id
            memory_id = runtime.add_memory(candidate.memory.to_memory_core())
            memory_ids.append(memory_id)
            if memory_id != candidate.memory.retention_id:
                self.team_retention_store.reinforce_review(memory_id, observed_at=event.occurred_at)
                continue
            self.team_retention_store.insert_memory(candidate.memory)
            self.team_retention_store.create_review_schedule(candidate.memory)
            if version_decision.should_supersede and version_decision.old_memory_id:
                self.version_manager.apply_supersede(version_decision.old_memory_id, memory_id)
        return DomainIngestResult(
            memory_ids=memory_ids,
            candidate_count=len(candidates),
            message="team_retention extractor enabled" if candidates else None,
        )

    def retrieve(self, query: RetrievalQuery, *, top_k: int) -> list[RankedMemory]:
        results = self.retriever.retrieve(query, limit=top_k)
        return [result.to_ranked_memory(rank=index + 1) for index, result in enumerate(results)]

    def update_memory(self, action: str, **kwargs: Any) -> DomainUpdateResult | None:
        memory_id = kwargs.get("memory_id")
        if action in {"expire", "forget"} and memory_id:
            self.team_retention_store.deactivate_review(memory_id)
            return None
        if action == "reviewed":
            if memory_id is None:
                raise ValueError("memory_id is required")
            next_review_at = self.team_retention_store.mark_reviewed(
                memory_id,
                reviewed_at=kwargs.get("reviewed_at"),
            )
            return DomainUpdateResult(
                action=action,
                memory_id=memory_id,
                updated=True,
                message=f"next_review_at={next_review_at}",
            )
        if action == "snooze":
            if memory_id is None:
                raise ValueError("memory_id is required")
            next_review_at = self.team_retention_store.snooze_review(
                memory_id,
                days=kwargs.get("snooze_days") or 1,
                now=kwargs.get("reviewed_at"),
            )
            return DomainUpdateResult(
                action=action,
                memory_id=memory_id,
                updated=True,
                message=f"next_review_at={next_review_at}",
            )
        return None

    def proactive_suggestions(self, **kwargs: Any) -> list[dict[str, Any]]:
        due = self.team_retention_store.list_due_reviews(
            now=kwargs.get("now"),
            warning_window_hours=kwargs.get("warning_window_hours", 24),
            team_id=kwargs.get("team_id"),
            project_id=kwargs.get("project_id"),
            workspace_id=kwargs.get("workspace_id"),
            limit=kwargs.get("limit", 10),
        )
        rows = {
            row["memory_id"]: row
            for row in self.memory_store.batch_get_memories([item.memory_id for item in due])
            if row.get("status") == "active" and row.get("domain") == self.domain
        }
        suggestions: list[dict[str, Any]] = []
        for schedule in due:
            if schedule.memory_id not in rows:
                continue
            memory = self.team_retention_store.get_memory(schedule.memory_id)
            if memory is None:
                continue
            suggestions.append(
                {
                    "suggestion_id": new_id("sug"),
                    "type": "review_reminder",
                    "title": "Team memory review reminder",
                    "content": memory.fact_value,
                    "priority": "high" if memory.risk_level == "high" else "normal",
                    "memory_id": memory.retention_id,
                    "due_at": schedule.next_review_at,
                    "metadata": {
                        "domain": self.domain,
                        "fact_type": memory.fact_type,
                        "risk_level": memory.risk_level,
                        "team_id": memory.team_id,
                        "project_id": memory.project_id,
                        "review_count": schedule.review_count,
                        "card": memory.to_card(),
                    },
                }
            )
        return suggestions

    def scan_review_due(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.proactive_suggestions(**kwargs)

    def _find_duplicate(self, memory: TeamRetentionMemory) -> str | None:
        if not memory.version_group:
            return None
        existing = self.team_retention_store.list_memories(
            team_id=memory.team_id,
            project_id=memory.project_id,
            workspace_id=memory.workspace_id,
            fact_type=memory.fact_type,
            version_group=memory.version_group,
            limit=20,
        )
        for item in existing:
            if item.fact_value.strip() == memory.fact_value.strip():
                row = self.memory_store.get_memory(item.retention_id)
                if row is not None and row.get("status") == "active":
                    return item.retention_id
        return None
