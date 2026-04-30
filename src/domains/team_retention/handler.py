from __future__ import annotations

from typing import Any

from src.core.domain_handler import DomainIngestResult, DomainRuntime, DomainUpdateResult
from src.retrieval import RankedMemory, RetrievalQuery
from src.schemas import NormalizedEvent
from src.storage import MemoryCoreStore, TeamRetentionStore
from src.utils.ids import new_id

from .admission import TeamRetentionAdmissionDecider
from .embedding import TeamRetentionEmbeddingIndexer
from .extractor import TeamRetentionExtractor
from .lifecycle import TeamRetentionLifecycleResolver
from .llm_extractor import TeamRetentionLLMExtraction, TeamRetentionLLMExtractor
from .models import TeamRetentionMemory
from .preprocessor import TeamRetentionRulePreprocessor
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
        self.llm_client = llm_client
        self.preprocessor = TeamRetentionRulePreprocessor()
        self.admission_decider = TeamRetentionAdmissionDecider()

    def ingest_event(self, event: NormalizedEvent, runtime: DomainRuntime) -> DomainIngestResult:
        if self.llm_client is not None:
            return self._ingest_event_with_llm(event, runtime)
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

    def _ingest_event_with_llm(self, event: NormalizedEvent, runtime: DomainRuntime) -> DomainIngestResult:
        preprocess = self.preprocessor.preprocess(event)
        extraction = TeamRetentionLLMExtractor(self.llm_client).extract(event, preprocess)
        if extraction is None:
            return self._ingest_event_with_rules(event, runtime)
        admission = self.admission_decider.decide(
            extraction,
            sensitive_unmasked=preprocess.features.sensitive_detected and not preprocess.features.sensitive_masked,
        )
        if admission.status == "reject":
            return DomainIngestResult(candidate_count=0, message=f"team_retention rejected: {admission.reason}")

        memory = self._memory_from_llm(event, extraction, admission.status)
        memory.confidence = admission.confidence
        memory.importance = admission.importance
        memory.metadata.update(
            {
                "llm_decision": extraction.decision,
                "final_decision": admission.status,
                "final_score": admission.score,
                "score_breakdown": dict(extraction.score_breakdown),
                "needs_confirmation": extraction.needs_confirmation or admission.status == "candidate",
                "primary_entity": dict(extraction.primary_entity),
                "topic_key": extraction.topic_key,
                "evidence_text": extraction.evidence_text,
                "rule_features": preprocess.features.to_dict(),
            }
        )

        embedding_indexer = TeamRetentionEmbeddingIndexer(runtime.embedding_store)
        lifecycle = TeamRetentionLifecycleResolver(self.memory_store, self.team_retention_store, embedding_indexer).resolve(memory)
        final_status = lifecycle.status or admission.status
        if lifecycle.action == "conflict" and lifecycle.matched_memory_id:
            final_status = "candidate"
            memory.metadata["conflict_with"] = lifecycle.matched_memory_id
            memory.metadata["needs_confirmation"] = True
        if lifecycle.action == "supersede" and lifecycle.matched_memory_id:
            memory.overwrite_of = lifecycle.matched_memory_id
        if lifecycle.action == "reinforce" and lifecycle.matched_memory_id:
            self._reinforce_existing(lifecycle.matched_memory_id, observed_at=event.occurred_at)
            old = self.team_retention_store.get_memory(lifecycle.matched_memory_id)
            if old is not None:
                embedding_indexer.upsert(old, status=final_status)
            return DomainIngestResult(
                memory_ids=[lifecycle.matched_memory_id],
                candidate_count=1,
                message="team_retention reinforced",
            )

        memory_core = memory.to_memory_core()
        memory_core.status = final_status  # type: ignore[assignment]
        memory_id = runtime.add_memory(memory_core)
        if memory_id != memory.retention_id:
            self._reinforce_existing(memory_id, observed_at=event.occurred_at)
            return DomainIngestResult(memory_ids=[memory_id], candidate_count=1, message="team_retention reinforced")

        self.team_retention_store.insert_memory(memory)
        if lifecycle.action == "supersede" and lifecycle.matched_memory_id:
            self.version_manager.apply_supersede(lifecycle.matched_memory_id, memory_id)
        if final_status == "active":
            self.team_retention_store.create_review_schedule(memory)
            memory = self.team_retention_store.get_memory(memory.retention_id) or memory
        embedding_indexer.upsert(memory, status=final_status)
        return DomainIngestResult(
            memory_ids=[memory_id],
            candidate_count=1,
            message=f"team_retention {final_status}",
        )

    def _ingest_event_with_rules(self, event: NormalizedEvent, runtime: DomainRuntime) -> DomainIngestResult:
        candidates = self.extractor.extract(event)
        memory_ids: list[str] = []
        for candidate in candidates:
            memory_core = candidate.memory.to_memory_core()
            memory_id = runtime.add_memory(memory_core)
            memory_ids.append(memory_id)
            if memory_id == candidate.memory.retention_id:
                self.team_retention_store.insert_memory(candidate.memory)
                self.team_retention_store.create_review_schedule(candidate.memory)
                TeamRetentionEmbeddingIndexer(runtime.embedding_store).upsert(candidate.memory, status=memory_core.status)
        return DomainIngestResult(
            memory_ids=memory_ids,
            candidate_count=len(candidates),
            message="team_retention rule fallback" if candidates else None,
        )

    def _memory_from_llm(
        self,
        event: NormalizedEvent,
        extraction: TeamRetentionLLMExtraction,
        status: str,
    ) -> TeamRetentionMemory:
        version_group = self._version_group(event, extraction)
        return TeamRetentionMemory(
            team_id=event.context.team_id,
            project_id=event.context.project_id,
            workspace_id=event.context.workspace_id,
            thread_id=event.context.thread_id,
            fact_type=extraction.fact_type,  # type: ignore[arg-type]
            fact_value=extraction.fact_value,
            risk_level=extraction.risk_level,  # type: ignore[arg-type]
            owner=extraction.owner,
            remember_reason=extraction.reason,
            review_policy=extraction.review_policy,  # type: ignore[arg-type]
            expiry_time=extraction.valid_to,
            version_group=version_group,
            source_event_id=event.event_id,
            source_type=event.source_type,
            source_ref=event.context.thread_id or event.event_id,
            valid_from=extraction.valid_from or event.occurred_at,
            tags=[f"llm_status:{status}"],
            confidence=extraction.confidence,
            importance=extraction.importance,
            created_at=event.occurred_at,
        )

    def _version_group(self, event: NormalizedEvent, extraction: TeamRetentionLLMExtraction) -> str:
        scope = event.context.team_id or event.context.project_id or event.context.workspace_id or "global"
        entity = extraction.primary_entity.get("normalized_key") or extraction.primary_entity.get("name") or "unknown"
        topic = extraction.topic_key or extraction.version_group_hint or extraction.fact_type
        return f"{scope}:{extraction.fact_type}:{entity}:{topic}".lower()

    def _reinforce_existing(self, memory_id: str, *, observed_at: str | None = None) -> None:
        existing = self.team_retention_store.get_memory(memory_id)
        if existing is None:
            raise ValueError(f"team retention memory not found: {memory_id}")
        if self.team_retention_store.get_review_schedule(memory_id) is not None:
            self.team_retention_store.reinforce_review(memory_id, observed_at=observed_at)
            return
        metadata = dict(existing.metadata)
        metadata["reinforce_count"] = int(metadata.get("reinforce_count") or 0) + 1
        if observed_at is not None:
            metadata["last_reinforced_at"] = observed_at
        self.team_retention_store.update_memory_metadata(memory_id, metadata)

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
