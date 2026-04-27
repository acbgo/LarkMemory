from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from src.core.access_tracker import AccessTracker
from src.core.admission_control import AdmissionController
from src.core.decay import DecayPolicy
from src.core.dedup_merge import DedupMergeEngine
from src.core.router import DomainRouter
from src.core.scheduler import ScheduledTaskResult, Scheduler
from src.core.supersede import SupersedeManager
from src.domains.project_decision import (
    ProjectDecisionExtractor,
    ProjectDecisionVersionManager,
)
from src.domains.team_retention import (
    TeamRetentionExtractor,
    TeamRetentionRetriever,
    TeamRetentionVersionManager,
)
from src.retrieval import (
    FusedCandidate,
    IntentAnalyzer,
    QueryRewriter,
    RankedMemory,
    RetrievalQuery,
    Reranker,
    memory_item_from_core,
)
from src.schemas import MemoryCore, NormalizedEvent
from src.storage import EmbeddingStore, EventStore, MemoryCoreStore, TeamRetentionStore
from src.utils.ids import new_id, query_id as new_query_id


@dataclass(slots=True)
class IngestResult:
    event_id: str
    stored: bool
    memory_ids: list[str] = field(default_factory=list)
    candidate_count: int = 0
    message: str | None = None


@dataclass(slots=True)
class RetrieveResult:
    query_id: str
    ranked_memories: list[RankedMemory] = field(default_factory=list)
    trace: dict[str, Any] | None = None
    message: str | None = None


@dataclass(slots=True)
class UpdateResult:
    action: str
    memory_id: str | None = None
    updated: bool = False
    message: str | None = None


class MemoryService:
    def __init__(
        self,
        *,
        event_store: EventStore,
        memory_store: MemoryCoreStore,
        team_retention_store: TeamRetentionStore | None = None,
        embedding_store: EmbeddingStore | None = None,
        llm_client: Any | None = None,
        router: DomainRouter | None = None,
        admission: AdmissionController | None = None,
        dedup: DedupMergeEngine | None = None,
        supersede: SupersedeManager | None = None,
        decay_policy: DecayPolicy | None = None,
        access_tracker: AccessTracker | None = None,
        project_decision_extractor: ProjectDecisionExtractor | None = None,
        project_decision_version_manager: ProjectDecisionVersionManager | None = None,
        team_retention_extractor: TeamRetentionExtractor | None = None,
        team_retention_retriever: TeamRetentionRetriever | None = None,
        team_retention_version_manager: TeamRetentionVersionManager | None = None,
    ) -> None:
        self.event_store = event_store
        self.memory_store = memory_store
        self.team_retention_store = team_retention_store or TeamRetentionStore(memory_store.db_path)
        self.team_retention_store.create_table()
        self.embedding_store = embedding_store
        self.llm_client = llm_client
        self.router = router or DomainRouter()
        self.admission = admission or AdmissionController()
        self.dedup = dedup or DedupMergeEngine()
        self.supersede = supersede or SupersedeManager(memory_store)
        self.decay_policy = decay_policy or DecayPolicy()
        self.access_tracker = access_tracker or AccessTracker()
        self.project_decision_extractor = project_decision_extractor or ProjectDecisionExtractor(
            llm_client=llm_client
        )
        self.project_decision_version_manager = (
            project_decision_version_manager
            or ProjectDecisionVersionManager(memory_store)
        )
        self.team_retention_extractor = team_retention_extractor or TeamRetentionExtractor(
            llm_client=llm_client
        )
        self.team_retention_retriever = team_retention_retriever or TeamRetentionRetriever(
            memory_store,
            self.team_retention_store,
        )
        self.team_retention_version_manager = (
            team_retention_version_manager
            or TeamRetentionVersionManager(memory_store, self.team_retention_store)
        )

    def ingest_event(self, event: NormalizedEvent) -> IngestResult:
        event_id = self.event_store.insert_event(event)
        route_decision = self.router.route_event(event)
        primary_domain = route_decision.primary[0].domain if route_decision.primary else None
        self.admission.evaluate_event(event, domain=primary_domain)
        memory_ids: list[str] = []
        candidates = []
        if primary_domain == "project_decision":
            candidates = self.project_decision_extractor.extract(event)
            for candidate in candidates:
                version_decision = self.project_decision_version_manager.detect_update(
                    candidate.decision
                )
                if version_decision.should_supersede and version_decision.old_memory_id:
                    candidate.decision.overwrite_of = version_decision.old_memory_id
                memory_id = self.add_memory(candidate.decision.to_memory_core())
                memory_ids.append(memory_id)
                if (
                    version_decision.should_supersede
                    and version_decision.old_memory_id
                    and memory_id == candidate.decision.decision_id
                ):
                    self.project_decision_version_manager.apply_supersede(
                        version_decision.old_memory_id,
                        memory_id,
                    )
        elif primary_domain == "team_retention":
            candidates = self.team_retention_extractor.extract(event)
            for candidate in candidates:
                duplicate_retention_id = self._find_duplicate_team_retention(candidate.memory)
                if duplicate_retention_id is not None:
                    memory_ids.append(duplicate_retention_id)
                    self.team_retention_store.reinforce_review(
                        duplicate_retention_id,
                        observed_at=event.occurred_at,
                    )
                    continue
                version_decision = self.team_retention_version_manager.detect_update(
                    candidate.memory
                )
                if version_decision.should_supersede and version_decision.old_memory_id:
                    candidate.memory.overwrite_of = version_decision.old_memory_id
                memory = candidate.memory.to_memory_core()
                memory_id = self.add_memory(memory)
                memory_ids.append(memory_id)
                if memory_id == candidate.memory.retention_id:
                    self.team_retention_store.insert_memory(candidate.memory)
                    self.team_retention_store.create_review_schedule(candidate.memory)
                    if (
                        version_decision.should_supersede
                        and version_decision.old_memory_id
                    ):
                        self.team_retention_version_manager.apply_supersede(
                            version_decision.old_memory_id,
                            memory_id,
                        )
                else:
                    self.team_retention_store.reinforce_review(
                        memory_id,
                        observed_at=event.occurred_at,
                    )
        return IngestResult(
            event_id=event_id,
            stored=True,
            memory_ids=memory_ids,
            candidate_count=len(candidates),
            message=f"event stored; {primary_domain} extractor enabled"
            if candidates
            else "event stored; no memory candidate admitted",
        )

    def add_memory(self, memory: MemoryCore) -> str:
        admission = self.admission.evaluate_memory(memory)
        if not admission.admitted:
            raise ValueError(f"memory rejected: {admission.reason}")
        existing = [
            *self.memory_store.search_memory_candidates(domain=memory.domain, status="active"),
            *self.memory_store.search_memory_candidates(domain=memory.domain, status="candidate"),
        ]
        duplicate = self.dedup.find_duplicate(memory, existing)
        if duplicate.duplicate_found and duplicate.matched_memory_id:
            return duplicate.matched_memory_id
        return self.memory_store.insert_memory_core(memory)

    def retrieve(
        self,
        query: RetrievalQuery,
        *,
        top_k: int = 10,
        include_trace: bool = False,
    ) -> RetrieveResult:
        if top_k < 1:
            raise ValueError("top_k must be greater than 0")
        query_id = new_query_id()
        intent = _run_async(IntentAnalyzer(self.llm_client).analyze(query))
        primary_domains = {domain.value for domain in intent.primary_domains}
        scoped_query = bool(query.team_id or query.project_id or query.workspace_id)
        explicit_team_intent = bool(intent.keywords or scoped_query)
        if "team_retention" in primary_domains and explicit_team_intent:
            results = self.team_retention_retriever.retrieve(query, limit=top_k)
            ranked = [result.to_ranked_memory(rank=index + 1) for index, result in enumerate(results)]
            for result in ranked:
                self.access_tracker.record_access(result.item.memory_id, query_id=query_id)
            trace = None
            if include_trace:
                trace = {
                    "mode": "team_retention",
                    "candidate_count": len(results),
                    "result_count": len(ranked),
                    "intent": [domain.value for domain in intent.primary_domains],
                }
            return RetrieveResult(
                query_id=query_id,
                ranked_memories=ranked,
                trace=trace,
                message="team_retention retriever",
            )
        rewritten = _run_async(QueryRewriter(self.llm_client).rewrite(query, intent))
        rows = self._filter_rows_by_query_scope(
            self.memory_store.list_active_memories(limit=max(top_k * 5, 20)),
            query,
        )
        candidates = [
            FusedCandidate(
                item=memory_item_from_core(row),
                source_domain=memory_item_from_core(row).domain,
                domain_rank=index + 1,
                fusion_score=1.0 / (index + 1),
            )
            for index, row in enumerate(rows)
        ]
        ranked = _run_async(Reranker(llm_client=None).rerank(candidates, rewritten, top_k=top_k))
        for result in ranked:
            self.access_tracker.record_access(result.item.memory_id, query_id=query_id)
        trace = None
        if include_trace:
            trace = {
                "mode": "memory_core_fallback",
                "candidate_count": len(candidates),
                "result_count": len(ranked),
            }
        return RetrieveResult(
            query_id=query_id,
            ranked_memories=ranked,
            trace=trace,
            message="memory_core fallback; domain retrievers not implemented",
        )

    def update_memory(
        self,
        action: str,
        *,
        memory_id: str | None = None,
        new_memory_id: str | None = None,
        confidence: float | None = None,
        importance: float | None = None,
        feedback_signal: str | None = None,
        reviewed_at: str | None = None,
        snooze_days: int | None = None,
    ) -> UpdateResult:
        if action in {"expire", "forget"}:
            if memory_id is None:
                raise ValueError("memory_id is required")
            self._require_memory_exists(memory_id)
            self.memory_store.update_memory_status(memory_id, "expired" if action == "expire" else "forgotten")
            self.team_retention_store.deactivate_review(memory_id)
            return UpdateResult(action=action, memory_id=memory_id, updated=True)
        if action == "supersede":
            if memory_id is None or new_memory_id is None:
                raise ValueError("memory_id and new_memory_id are required")
            self._require_memory_exists(memory_id)
            self._require_memory_exists(new_memory_id)
            self.supersede.mark_superseded(memory_id, new_memory_id)
            return UpdateResult(action=action, memory_id=memory_id, updated=True)
        if action == "confidence":
            if memory_id is None or confidence is None:
                raise ValueError("memory_id and confidence are required")
            self._require_memory_exists(memory_id)
            self.memory_store.update_confidence(memory_id, confidence)
            return UpdateResult(action=action, memory_id=memory_id, updated=True)
        if action == "importance":
            if memory_id is None or importance is None:
                raise ValueError("memory_id and importance are required")
            self._require_memory_exists(memory_id)
            self.memory_store.update_importance(memory_id, importance)
            return UpdateResult(action=action, memory_id=memory_id, updated=True)
        if action == "feedback":
            if memory_id is None or feedback_signal is None:
                raise ValueError("memory_id and feedback_signal are required")
            self.access_tracker.record_feedback(memory_id, feedback_signal)
            return UpdateResult(action=action, memory_id=memory_id, updated=False, message="feedback recorded")
        if action == "reviewed":
            if memory_id is None:
                raise ValueError("memory_id is required")
            next_review_at = self.team_retention_store.mark_reviewed(
                memory_id,
                reviewed_at=reviewed_at,
            )
            self.access_tracker.record_feedback(memory_id, feedback_signal or "reviewed")
            return UpdateResult(
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
                days=snooze_days or 1,
                now=reviewed_at,
            )
            return UpdateResult(
                action=action,
                memory_id=memory_id,
                updated=True,
                message=f"next_review_at={next_review_at}",
            )
        raise ValueError(f"unsupported action: {action}")

    def proactive_suggestions(
        self,
        *,
        user_id: str | None = None,
        project_id: str | None = None,
        team_id: str | None = None,
        workspace_id: str | None = None,
        limit: int = 10,
        now: str | None = None,
        warning_window_hours: int = 24,
    ) -> list[dict[str, Any]]:
        del user_id
        due = self.team_retention_store.list_due_reviews(
            now=now,
            warning_window_hours=warning_window_hours,
            team_id=team_id,
            project_id=project_id,
            workspace_id=workspace_id,
            limit=limit,
        )
        memory_ids = [item.memory_id for item in due]
        rows = {
            row["memory_id"]: row
            for row in self.memory_store.batch_get_memories(memory_ids)
            if row.get("status") == "active" and row.get("domain") == "team_retention"
        }
        suggestions: list[dict[str, Any]] = []
        for schedule in due:
            row = rows.get(schedule.memory_id)
            if row is None:
                continue
            memory = self.team_retention_store.get_memory(schedule.memory_id)
            if memory is None:
                continue
            priority = "high" if memory.risk_level == "high" else "normal"
            suggestions.append(
                {
                    "suggestion_id": new_id("sug"),
                    "type": "review_reminder",
                    "title": "Team memory review reminder",
                    "content": memory.fact_value,
                    "priority": priority,
                    "memory_id": memory.retention_id,
                    "due_at": schedule.next_review_at,
                    "metadata": {
                        "domain": "team_retention",
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

    def run_maintenance(self) -> dict[str, ScheduledTaskResult]:
        return Scheduler(
            self.memory_store,
            self.decay_policy,
            team_retention_store=self.team_retention_store,
        ).run_once()

    def _require_memory_exists(self, memory_id: str) -> None:
        if self.memory_store.get_memory(memory_id) is None:
            raise ValueError(f"memory not found: {memory_id}")

    def _filter_rows_by_query_scope(
        self,
        rows: list[dict[str, Any]],
        query: RetrievalQuery,
    ) -> list[dict[str, Any]]:
        scoped_query = bool(query.team_id or query.project_id or query.workspace_id or query.user_id)
        result: list[dict[str, Any]] = []
        for row in rows:
            if row.get("domain") == "team_retention" and not scoped_query:
                continue
            terms = [
                *(row.get("entities") or row.get("entities_json") or []),
                row.get("source_ref") or "",
            ]
            if query.team_id and not self._row_has_scope(terms, "team_id", query.team_id):
                continue
            if query.project_id and not self._row_has_scope(terms, "project_id", query.project_id):
                continue
            if query.workspace_id and not self._row_has_scope(terms, "workspace_id", query.workspace_id):
                continue
            if query.user_id and row.get("scope") == "user" and not self._row_has_scope(terms, "user_id", query.user_id):
                continue
            result.append(row)
        return result

    def _row_has_scope(self, terms: list[str], key: str, value: str) -> bool:
        return value in terms or f"{key}:{value}" in terms

    def _find_duplicate_team_retention(self, memory: Any) -> str | None:
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


def _run_async(awaitable: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    else:
        raise RuntimeError("MemoryService sync API cannot run inside an active event loop")
