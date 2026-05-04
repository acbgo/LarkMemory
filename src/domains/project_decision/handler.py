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
        self.version_manager = version_manager or ProjectDecisionVersionManager(memory_store)

    def ingest_event(self, event: NormalizedEvent, runtime: DomainRuntime) -> DomainIngestResult:
        logger.info(
            "action=start event_id=%s",
            event.event_id,
        )
        candidates = self.extractor.extract(event)
        memory_ids: list[str] = []
        for candidate in candidates:
            version_decision = self.version_manager.detect_update(candidate.decision)
            if version_decision.should_supersede and version_decision.old_memory_id:
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
                "action=stored event_id=%s memory_id=%s topic=%s",
                event.event_id,
                memory_id,
                candidate.decision.topic,
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
