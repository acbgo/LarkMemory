from __future__ import annotations

import logging
from typing import Any

from src.core.domain_handler import DomainIngestResult, DomainRuntime, DomainUpdateResult
from src.retrieval import RankedMemory, RetrievalQuery
from src.schemas import NormalizedEvent
from src.storage import CLIWorkflowStore, MemoryCoreStore

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
        cli_store: CLIWorkflowStore | None = None,
        retriever: CLIWorkflowRetriever | None = None,
        version_manager: CLIWorkflowVersionManager | None = None,
    ) -> None:
        self.memory_store = memory_store
        self.cli_store = cli_store
        self.extractor = extractor or CLIWorkflowExtractor(llm_client=llm_client, memory_store=memory_store)
        self.retriever = retriever or CLIWorkflowRetriever(memory_store, cli_store=cli_store)
        self.version_manager = version_manager or CLIWorkflowVersionManager(memory_store)

    def ingest_event(self, event: NormalizedEvent, runtime: DomainRuntime) -> DomainIngestResult:
        """写入 CLI 工作流记忆，并同步结构化命令模式/主动参数策略表。"""
        logger.info(
            "action=start event_id=%s source_type=%s",
            event.event_id,
            event.source_type,
        )
        candidates = self.extractor.extract(event)
        policy_ids = self._store_openclaw_parameter_policies(event)
        if not candidates:
            logger.info(
                "action=done event_id=%s reason=no_candidates policy_count=%s",
                event.event_id,
                len(policy_ids),
            )
            return DomainIngestResult(
                candidate_count=len(policy_ids),
                message="cli parameter policy stored" if policy_ids else "no cli workflow candidates extracted",
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
                self._store_command_pattern(event, candidate, version_decision.old_memory_id)
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
            self._store_command_pattern(event, candidate, memory_id)

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
            candidate_count=len(candidates) + len(policy_ids),
            message="cli_workflow extractor enabled" if candidates else None,
        )

    def _store_openclaw_parameter_policies(self, event: NormalizedEvent) -> list[str]:
        """从 OpenClaw 主动教学文本中记录显式参数策略。"""
        if self.cli_store is None or event.source_type != "openclaw":
            return []
        user_id = event.context.user_id or ""
        if not user_id:
            return []
        return self.cli_store.upsert_parameter_policy_from_text(
            event.content_text or "",
            user_id=user_id,
            project_id=event.context.project_id,
        )

    def _store_command_pattern(
        self,
        event: NormalizedEvent,
        candidate: Any,
        memory_id_value: str,
    ) -> None:
        """把通过准入的命令记忆同步进结构化命令模式表。"""
        if self.cli_store is None:
            return
        self.cli_store.upsert_pattern(
            candidate.memory,
            memory_id_value=memory_id_value,
            cwd=str(event.payload.get("cwd") or "") if event.payload else None,
            semantic_description=candidate.evidence_text,
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
