from __future__ import annotations

import logging
from typing import Any

from src.core.domain_handler import DomainIngestResult, DomainRuntime, DomainUpdateResult
from src.llm import EmbeddingClient, RerankClient
from src.retrieval import RankedMemory, RetrievalQuery
from src.schemas import NormalizedEvent
from src.storage import EmbeddingStore, MemoryCoreStore

from .embedding import ProjectDecisionEmbeddingIndexer
from .extractor import ProjectDecisionExtractor
from .retriever import ProjectDecisionRetriever
from .versioning import ProjectDecisionVersionManager


logger = logging.getLogger(__name__)


class ProjectDecisionDomainHandler:
    domain = "project_decision"

    def __init__(
        self,
        memory_store: MemoryCoreStore,
        *,
        embedding_store: EmbeddingStore | None = None,
        embedding_client: EmbeddingClient | None = None,
        rerank_client: RerankClient | None = None,
        llm_client: Any | None = None,
        extractor: ProjectDecisionExtractor | None = None,
        retriever: ProjectDecisionRetriever | None = None,
        version_manager: ProjectDecisionVersionManager | None = None,
    ) -> None:
        self.memory_store = memory_store
        self.embedding_store = embedding_store
        self.embedding_client = embedding_client
        self.rerank_client = rerank_client
        self.extractor = extractor or ProjectDecisionExtractor(llm_client=llm_client)
        self.retriever = retriever or ProjectDecisionRetriever(
            memory_store,
            embedding_store=embedding_store,
            embedding_client=embedding_client,
            rerank_client=rerank_client,
        )
        self.version_manager = version_manager or ProjectDecisionVersionManager(
            memory_store,
            llm_client=llm_client,
        )

    def ingest_event(self, event: NormalizedEvent, runtime: DomainRuntime) -> DomainIngestResult:
        logger.info(
            "action=start event_id=%s",
            event.event_id,
        )
        candidates = self.extractor.extract(event)
        memory_ids: list[str] = []
        for candidate in candidates:
            version_decision = self._resolve_version_decision(candidate.decision, runtime)
            if version_decision.should_reuse_existing and version_decision.old_memory_id:
                memory_ids.append(version_decision.old_memory_id)
                logger.info(
                    "action=duplicate_detected event_id=%s dedup_action=duplicate memory_id=%s matched_memory_id=%s topic=%s reason=%s confidence=%s source=%s",
                    event.event_id,
                    version_decision.old_memory_id,
                    version_decision.old_memory_id,
                    candidate.decision.topic,
                    version_decision.reason,
                    version_decision.confidence,
                    version_decision.detection_source,
                )
                continue
            if version_decision.should_supersede and version_decision.old_memory_id:
                logger.info(
                    "action=supersede_detected event_id=%s dedup_action=supersede old_memory_id=%s new_memory_id=%s topic=%s reason=%s confidence=%s source=%s",
                    event.event_id,
                    version_decision.old_memory_id,
                    candidate.decision.decision_id,
                    candidate.decision.topic,
                    version_decision.reason,
                    version_decision.confidence,
                    version_decision.detection_source,
                )
                candidate.decision.overwrite_of = version_decision.old_memory_id
            memory_id = runtime.add_memory(candidate.decision.to_memory_core())
            memory_ids.append(memory_id)
            if (
                version_decision.should_supersede
                and version_decision.old_memory_id
                and memory_id == candidate.decision.decision_id
            ):
                self.version_manager.apply_supersede(version_decision.old_memory_id, memory_id)
            if memory_id == candidate.decision.decision_id:
                ProjectDecisionEmbeddingIndexer(
                    runtime.embedding_store or self.embedding_store,
                    runtime.embedding_client or self.embedding_client,
                ).upsert(
                    candidate.decision,
                    status="active",
                )
            logger.info(
                "action=stored event_id=%s memory_id=%s topic=%s dedup_action=%s",
                event.event_id,
                memory_id,
                candidate.decision.topic,
                "supersede_inserted" if version_decision.should_supersede else "inserted",
            )
        logger.info(
            "action=done event_id=%s candidate_count=%s memory_count=%s",
            event.event_id,
            len(candidates),
            len(memory_ids),
        )
        return DomainIngestResult(
            memory_ids=memory_ids,
            candidate_count=len(candidates),
            message="project_decision extractor enabled" if candidates else None,
        )

    def retrieve(self, query: RetrievalQuery, *, top_k: int) -> list[RankedMemory]:
        results = self.retriever.retrieve(query, limit=top_k)
        return [result.to_ranked_memory(rank=index + 1) for index, result in enumerate(results)]

    def update_memory(self, action: str, **kwargs: Any) -> DomainUpdateResult | None:
        return None

    def proactive_suggestions(self, **kwargs: Any) -> list[dict[str, Any]]:
        return []

    def scan_review_due(self, **kwargs: Any) -> list[dict[str, Any]]:
        return []

    def _resolve_version_decision(
        self,
        decision: Any,
        runtime: DomainRuntime,
    ) -> Any:
        semantic_rows = self._load_semantic_candidate_rows(decision, runtime)
        if semantic_rows:
            semantic_decision = self.version_manager.detect_update(
                decision,
                semantic_rows,
                detection_source="semantic",
            )
            if semantic_decision.should_reuse_existing or semantic_decision.should_supersede:
                return semantic_decision
        return self.version_manager.detect_update(decision, detection_source="rule")

    def _load_semantic_candidate_rows(
        self,
        decision: Any,
        runtime: DomainRuntime,
    ) -> list[dict[str, Any]]:
        embedding_store = runtime.embedding_store or self.embedding_store
        if embedding_store is None:
            return []
        indexer = ProjectDecisionEmbeddingIndexer(
            embedding_store,
            runtime.embedding_client or self.embedding_client,
        )
        try:
            hits = indexer.query_similar(decision, top_k=10)
        except Exception:
            logger.warning(
                "action=semantic_candidates_failed decision_id=%s topic=%s",
                decision.decision_id,
                decision.topic,
                exc_info=True,
            )
            return []
        candidate_ids: list[str] = []
        for hit in hits:
            memory_id = hit.get("memory_id") or hit.get("id")
            distance = hit.get("distance")
            if not isinstance(memory_id, str):
                continue
            if isinstance(distance, (int, float)) and float(distance) > 0.2:
                continue
            if memory_id == decision.decision_id or memory_id in candidate_ids:
                continue
            candidate_ids.append(memory_id)
        if not candidate_ids:
            return []
        rows = [
            row
            for row in self.memory_store.batch_get_memories(candidate_ids)
            if row.get("domain") == self.domain and row.get("status") == "active"
        ]
        logger.info(
            "action=semantic_candidates_loaded decision_id=%s topic=%s candidate_count=%s candidate_ids=%s",
            decision.decision_id,
            decision.topic,
            len(rows),
            [row["memory_id"] for row in rows],
        )
        return rows
