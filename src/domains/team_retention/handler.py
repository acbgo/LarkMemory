from __future__ import annotations

import logging
from typing import Any

from src.core.domain_handler import DomainIngestResult, DomainRuntime, DomainUpdateResult

logger = logging.getLogger(__name__)
from src.llm import EmbeddingClient
from src.retrieval import RankedMemory, RetrievalQuery
from src.schemas import NormalizedEvent
from src.storage import EmbeddingStore, MemoryCoreStore, TeamRetentionStore
from src.utils.ids import new_id

from .admission import TeamRetentionAdmissionDecision, TeamRetentionAdmissionDecider
from .embedding import TeamRetentionEmbeddingIndexer
from .extractor import TeamRetentionExtractor
from .lifecycle import TeamRetentionArbitrator
from .llm_extractor import TeamRetentionLLMExtraction, TeamRetentionLLMExtractor
from .models import TeamRetentionMemory
from .preprocessor import TeamRetentionRulePreprocessor
from .retriever import TeamRetentionRetriever
from .scoring import calculate_confidence, calculate_importance
from .versioning import TeamRetentionVersionManager


class TeamRetentionDomainHandler:
    domain = "team_retention"

    def __init__(
        self,
        memory_store: MemoryCoreStore,
        team_retention_store: TeamRetentionStore,
        *,
        embedding_store: EmbeddingStore | None = None,
        embedding_client: EmbeddingClient | None = None,
        llm_client: Any | None = None,
        extractor: TeamRetentionExtractor | None = None,
        retriever: TeamRetentionRetriever | None = None,
        version_manager: TeamRetentionVersionManager | None = None,
        arbitrator: Any | None = None,
    ) -> None:
        self.memory_store = memory_store
        self.team_retention_store = team_retention_store
        self.extractor = extractor or TeamRetentionExtractor(llm_client=llm_client)
        self.retriever = retriever or TeamRetentionRetriever(
            memory_store,
            team_retention_store,
            embedding_store=embedding_store,
            embedding_client=embedding_client,
        )
        self.version_manager = version_manager or TeamRetentionVersionManager(memory_store, team_retention_store)
        self.llm_client = llm_client
        self.preprocessor = TeamRetentionRulePreprocessor()
        self.admission_decider = TeamRetentionAdmissionDecider()
        embedding_indexer = TeamRetentionEmbeddingIndexer(embedding_store, embedding_client)
        if arbitrator is not None:
            self.arbitrator = arbitrator
        elif llm_client is not None:
            self.arbitrator = TeamRetentionArbitrator(llm_client, embedding_indexer)
        else:
            self.arbitrator = None
        self.embedding_indexer = embedding_indexer

    def ingest_event(self, event: NormalizedEvent, runtime: DomainRuntime) -> DomainIngestResult:
        if self.llm_client is not None:
            return self._ingest_event_with_llm(event, runtime)
        return self._ingest_event_with_rules(event, runtime)

    # ------------------------------------------------------------------
    # LLM path: two-stage pipeline
    # ------------------------------------------------------------------

    def _ingest_event_with_llm(self, event: NormalizedEvent, runtime: DomainRuntime) -> DomainIngestResult:
        logger.info("action=ingest_llm_start event_id=%s", event.event_id)
        preprocess = self.preprocessor.preprocess(event)

        extraction = TeamRetentionLLMExtractor(self.llm_client).extract(event, preprocess)
        if extraction is None:
            logger.info("action=llm_extraction_failed event_id=%s fallback=rule_based", event.event_id)
            return self._ingest_event_with_rules(event, runtime)

        confidence = calculate_confidence(extraction)
        importance = calculate_importance(extraction)

        logger.info(
            "action=stage1_extraction event_id=%s is_team_retention=%s fact_type=%s fact_value=%s "
            "certainty=%s evidence_quality=%s fact_specificity=%s risk_level=%s "
            "time_sensitivity=%s scope_impact=%s irreversibility=%s "
            "confidence=%.2f importance=%.2f",
            event.event_id,
            extraction.is_team_retention,
            extraction.fact_type,
            extraction.fact_value[:120] if extraction.fact_value else "",
            extraction.certainty,
            extraction.evidence_quality,
            extraction.fact_specificity,
            extraction.risk_level,
            extraction.time_sensitivity,
            extraction.scope_impact,
            extraction.irreversibility,
            confidence,
            importance,
        )

        admission = self.admission_decider.decide(extraction, confidence=confidence, importance=importance)
        logger.info(
            "action=admission event_id=%s status=%s confidence=%.2f importance=%.2f reason=%s",
            event.event_id,
            admission.status,
            confidence,
            importance,
            admission.reason,
        )
        if admission.status == "reject":
            return DomainIngestResult(candidate_count=0, message=f"team_retention rejected: {admission.reason}")

        memory = self._memory_from_llm(event, extraction)
        memory.confidence = confidence
        memory.importance = importance
        memory.metadata.update(
            {
                "final_decision": admission.status,
                "admission_reason": admission.reason,
                "needs_confirmation": admission.status == "candidate",
                "primary_entity": dict(extraction.primary_entity),
                "topic_key": extraction.topic_key,
                "evidence_text": extraction.evidence_text,
            }
        )

        if self.arbitrator is not None and admission.status == "active":
            pass  # arbitration path below
        else:
            logger.info(
                "action=stage2_skipped event_id=%s reason=%s",
                event.event_id,
                "arbitrator_unavailable" if self.arbitrator is None else f"admission_{admission.status}",
            )

        if self.arbitrator is not None and admission.status == "active":
            old_memories = self.arbitrator.load_old_memories(
                memory,
                get_memory_fn=self.team_retention_store.get_memory,
                top_k=3,
            )
            logger.info(
                "action=stage2_candidates event_id=%s old_count=%s old_ids=%s",
                event.event_id,
                len(old_memories),
                [m.retention_id for m in old_memories],
            )
            arbitration = self.arbitrator.arbitrate(memory, old_memories=old_memories)
            logger.info(
                "action=stage2_arbitration event_id=%s action=%s target_memory_id=%s reason=%s",
                event.event_id,
                arbitration.action,
                arbitration.target_memory_id,
                arbitration.reason,
            )

            if arbitration.action == "strengthen" and arbitration.target_memory_id:
                logger.info(
                    "action=final_decision event_id=%s decision=strengthen target=%s reason=%s",
                    event.event_id, arbitration.target_memory_id, arbitration.reason,
                )
                self._reinforce_existing(arbitration.target_memory_id, observed_at=event.occurred_at)
                self.embedding_indexer.upsert(memory, status="active")
                return DomainIngestResult(
                    memory_ids=[arbitration.target_memory_id],
                    candidate_count=1,
                    message=f"team_retention strengthened: {arbitration.reason}",
                )

            if arbitration.action == "update" and arbitration.target_memory_id:
                logger.info(
                    "action=final_decision event_id=%s decision=update target=%s reason=%s",
                    event.event_id, arbitration.target_memory_id, arbitration.reason,
                )
                memory.overwrite_of = arbitration.target_memory_id
            elif arbitration.action == "candidate":
                logger.info(
                    "action=final_decision event_id=%s decision=candidate reason=%s",
                    event.event_id, arbitration.reason,
                )
                admission = TeamRetentionAdmissionDecision("candidate", confidence, importance, arbitration.reason)
            else:
                logger.info(
                    "action=final_decision event_id=%s decision=add reason=%s",
                    event.event_id, arbitration.reason,
                )

        final_status = admission.status

        memory_core = memory.to_memory_core()
        memory_core.status = final_status
        memory_id = runtime.add_memory(memory_core)

        if memory_id != memory.retention_id:
            self._reinforce_existing(memory_id, observed_at=event.occurred_at)
            return DomainIngestResult(memory_ids=[memory_id], candidate_count=1, message="team_retention reinforced")

        self.team_retention_store.insert_memory(memory)

        if memory.overwrite_of:
            self.version_manager.apply_supersede(memory.overwrite_of, memory_id)

        if final_status == "active":
            self.team_retention_store.create_review_schedule(memory)

        self.embedding_indexer.upsert(memory, status=final_status)

        return DomainIngestResult(
            memory_ids=[memory_id],
            candidate_count=1,
            message=f"team_retention {final_status}: {admission.reason}",
        )

    # ------------------------------------------------------------------
    # Rule fallback path
    # ------------------------------------------------------------------

    def _ingest_event_with_rules(self, event: NormalizedEvent, runtime: DomainRuntime) -> DomainIngestResult:
        candidates = self.extractor.extract(event)
        memory_ids: list[str] = []
        for candidate in candidates:
            duplicate_id = self._find_duplicate(candidate.memory)
            if duplicate_id is not None:
                memory_ids.append(duplicate_id)
                self._reinforce_existing(duplicate_id, observed_at=event.occurred_at)
                continue
            version_decision = self.version_manager.detect_update(candidate.memory)
            if version_decision.should_supersede and version_decision.old_memory_id:
                candidate.memory.overwrite_of = version_decision.old_memory_id
            memory_core = candidate.memory.to_memory_core()
            memory_id = runtime.add_memory(memory_core)
            memory_ids.append(memory_id)
            if memory_id != candidate.memory.retention_id:
                self._reinforce_existing(memory_id, observed_at=event.occurred_at)
                continue
            if memory_id == candidate.memory.retention_id:
                self.team_retention_store.insert_memory(candidate.memory)
                self.team_retention_store.create_review_schedule(candidate.memory)
                if version_decision.should_supersede and version_decision.old_memory_id:
                    self.version_manager.apply_supersede(version_decision.old_memory_id, memory_id)
                TeamRetentionEmbeddingIndexer(runtime.embedding_store, runtime.embedding_client).upsert(
                    candidate.memory,
                    status=memory_core.status,
                )
        return DomainIngestResult(
            memory_ids=memory_ids,
            candidate_count=len(candidates),
            message="team_retention rule fallback" if candidates else None,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _memory_from_llm(
        self,
        event: NormalizedEvent,
        extraction: TeamRetentionLLMExtraction,
    ) -> TeamRetentionMemory:
        return TeamRetentionMemory(
            team_id=event.context.team_id,
            project_id=event.context.project_id,
            workspace_id=event.context.workspace_id,
            thread_id=event.context.thread_id,
            fact_type=extraction.fact_type,
            fact_value=extraction.fact_value,
            risk_level=extraction.risk_level,
            owner=extraction.owner,
            remember_reason=extraction.reason,
            review_policy=extraction.review_policy,
            expiry_time=extraction.valid_to,
            version_group=self._version_group(event, extraction),
            source_event_id=event.event_id,
            source_type=event.source_type,
            source_ref=event.context.thread_id or event.event_id,
            valid_from=extraction.valid_from or event.occurred_at,
            tags=[],
            confidence=0.0,
            importance=0.0,
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

    # ------------------------------------------------------------------
    # Retrieval, update, proactive
    # ------------------------------------------------------------------

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
