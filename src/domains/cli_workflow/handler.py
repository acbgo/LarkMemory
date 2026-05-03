from __future__ import annotations

import logging
from typing import Any

from src.core.domain_handler import DomainIngestResult, DomainRuntime, DomainUpdateResult
from src.retrieval import RankedMemory, RetrievalQuery
from src.schemas import NormalizedEvent
from src.storage import MemoryCoreStore

from .extractor import CLIWorkflowExtractor
from .retriever import CLIWorkflowRetriever
from .versioning import CLIWorkflowVersionManager


logger = logging.getLogger(__name__)


class CLIWorkflowDomainHandler:
    domain = "cli_workflow"

    def __init__(
        self,
        memory_store: MemoryCoreStore,
        *,
        llm_client: Any | None = None,
        extractor: CLIWorkflowExtractor | None = None,
        retriever: CLIWorkflowRetriever | None = None,
        version_manager: CLIWorkflowVersionManager | None = None,
    ) -> None:
        self.memory_store = memory_store
        self.extractor = extractor or CLIWorkflowExtractor(llm_client=llm_client)
        self.retriever = retriever or CLIWorkflowRetriever(memory_store)
        self.version_manager = version_manager or CLIWorkflowVersionManager(memory_store)

    def ingest_event(self, event: NormalizedEvent, runtime: DomainRuntime) -> DomainIngestResult:
        logger.info(
            "action=start event_id=%s source_type=%s",
            event.event_id,
            event.source_type,
        )
        candidates = self.extractor.extract(event)
        if not candidates:
            logger.info(
                "action=done event_id=%s reason=no_candidates",
                event.event_id,
            )
            return DomainIngestResult(
                candidate_count=0,
                message="no cli workflow candidates extracted",
            )

        memory_ids: list[str] = []
        for candidate in candidates:
            if not candidate.is_admissible():
                logger.info(
                    "action=candidate_filtered event_id=%s command=%s",
                    event.event_id,
                    candidate.memory.command_name,
                )
                continue
            version_decision = self.version_manager.detect_update(candidate.memory)

            if version_decision.should_reinforce and version_decision.old_memory_id:
                self.version_manager.apply_reinforce(
                    version_decision.old_memory_id,
                    candidate.memory,
                )
                memory_ids.append(version_decision.old_memory_id)
                logger.info(
                    "action=reinforced event_id=%s memory_id=%s message=%s",
                    event.event_id,
                    version_decision.old_memory_id,
                    version_decision.message,
                )
                continue

            if version_decision.should_supersede and version_decision.old_memory_id:
                candidate.memory.overwrite_of = version_decision.old_memory_id

            memory_id = runtime.add_memory(candidate.memory.to_memory_core())
            memory_ids.append(memory_id)

            if (
                version_decision.should_supersede
                and version_decision.old_memory_id
                and memory_id == candidate.memory.workflow_id
            ):
                self.version_manager.apply_supersede(
                    version_decision.old_memory_id,
                    memory_id,
                )

            logger.info(
                "action=stored event_id=%s memory_id=%s command=%s execution_count=%s",
                event.event_id,
                memory_id,
                candidate.memory.command_name,
                candidate.memory.execution_count,
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
            message="cli_workflow extractor enabled" if candidates else None,
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
