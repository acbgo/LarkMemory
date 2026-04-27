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
from src.storage import EmbeddingStore, EventStore, MemoryCoreStore
from src.utils.ids import query_id as new_query_id


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
    ) -> None:
        self.event_store = event_store
        self.memory_store = memory_store
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
        return IngestResult(
            event_id=event_id,
            stored=True,
            memory_ids=memory_ids,
            candidate_count=len(candidates),
            message="event stored; project_decision extractor enabled"
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
        rewritten = _run_async(QueryRewriter(self.llm_client).rewrite(query, intent))
        rows = self.memory_store.list_active_memories(limit=max(top_k * 5, 20))
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
    ) -> UpdateResult:
        if action in {"expire", "forget"}:
            if memory_id is None:
                raise ValueError("memory_id is required")
            self.memory_store.update_memory_status(memory_id, "expired" if action == "expire" else "forgotten")
            return UpdateResult(action=action, memory_id=memory_id, updated=True)
        if action == "supersede":
            if memory_id is None or new_memory_id is None:
                raise ValueError("memory_id and new_memory_id are required")
            self.supersede.mark_superseded(memory_id, new_memory_id)
            return UpdateResult(action=action, memory_id=memory_id, updated=True)
        if action == "confidence":
            if memory_id is None or confidence is None:
                raise ValueError("memory_id and confidence are required")
            self.memory_store.update_confidence(memory_id, confidence)
            return UpdateResult(action=action, memory_id=memory_id, updated=True)
        if action == "importance":
            if memory_id is None or importance is None:
                raise ValueError("memory_id and importance are required")
            self.memory_store.update_importance(memory_id, importance)
            return UpdateResult(action=action, memory_id=memory_id, updated=True)
        if action == "feedback":
            if memory_id is None or feedback_signal is None:
                raise ValueError("memory_id and feedback_signal are required")
            self.access_tracker.record_feedback(memory_id, feedback_signal)
            return UpdateResult(action=action, memory_id=memory_id, updated=False, message="feedback recorded")
        raise ValueError(f"unsupported action: {action}")

    def proactive_suggestions(
        self,
        *,
        user_id: str | None = None,
        project_id: str | None = None,
        team_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        del user_id, project_id, team_id, limit
        return []

    def run_maintenance(self) -> dict[str, ScheduledTaskResult]:
        return Scheduler(self.memory_store, self.decay_policy).run_once()


def _run_async(awaitable: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    else:
        raise RuntimeError("MemoryService sync API cannot run inside an active event loop")
