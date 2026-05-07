from __future__ import annotations

import logging
import re
from typing import Any

from src.core.domain_handler import DomainIngestResult, DomainRuntime, DomainUpdateResult

logger = logging.getLogger(__name__)
from src.llm import EmbeddingClient
from src.retrieval import RankedMemory, RetrievalQuery
from src.schemas import NormalizedEvent
from src.storage import EmbeddingStore, MemoryCoreStore, TeamRetentionStore
from src.utils.ids import new_id
from src.utils.text import clean_text
from src.utils.time import utc_now_iso

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
        notifier: Any | None = None,
        chat_id: str | None = None,
    ) -> None:
        self.memory_store = memory_store
        self.team_retention_store = team_retention_store
        self.extractor = extractor or TeamRetentionExtractor(llm_client=llm_client)
        self.retriever = retriever or TeamRetentionRetriever(
            memory_store,
            team_retention_store,
            embedding_store=embedding_store,
            embedding_client=embedding_client,
            decay_rate=0.001,
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
        self.notifier = notifier
        self.chat_id = chat_id

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
        if _is_retrieval_question(preprocess.raw_text):
            logger.info(
                "action=team_retention_query_skipped event_id=%s reason=retrieval_question",
                event.event_id,
            )
            return DomainIngestResult(candidate_count=0, message="team_retention query skipped")

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
                "evidence_text": extraction.evidence_text or preprocess.raw_text,
            }
        )

        structured_conflict = self._detect_structured_conflict(memory)
        if structured_conflict is not None:
            old_memory, reason = structured_conflict
            memory.metadata.update(
                {
                    "conflict_with": old_memory.retention_id,
                    "conflict_reason": reason,
                }
            )
            if _has_explicit_update_signal(preprocess.raw_text):
                memory.overwrite_of = old_memory.retention_id
                admission = TeamRetentionAdmissionDecision(
                    "active",
                    confidence,
                    importance,
                    f"structured_update:{reason}",
                )
                logger.info(
                    "action=structured_conflict_update event_id=%s target=%s reason=%s",
                    event.event_id,
                    old_memory.retention_id,
                    reason,
                )
            else:
                admission = TeamRetentionAdmissionDecision(
                    "candidate",
                    confidence,
                    importance,
                    f"structured_conflict_requires_confirmation:{reason}",
                )
                logger.info(
                    "action=structured_conflict_candidate event_id=%s target=%s reason=%s",
                    event.event_id,
                    old_memory.retention_id,
                    reason,
                )
            memory.metadata.update(
                {
                    "final_decision": admission.status,
                    "admission_reason": admission.reason,
                    "needs_confirmation": admission.status == "candidate",
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
                strengthened = self._reinforce_existing(arbitration.target_memory_id, observed_at=event.occurred_at)
                self._maybe_send_strengthened_card(strengthened)
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

        duplicate_id = self._find_duplicate(memory, allowed_statuses={"active", "candidate"})
        if duplicate_id is not None:
            strengthened = self._reinforce_existing(duplicate_id, observed_at=event.occurred_at)
            self._maybe_send_strengthened_card(strengthened)
            return DomainIngestResult(
                memory_ids=[duplicate_id],
                candidate_count=1,
                message="team_retention reinforced duplicate",
            )

        memory_core = memory.to_memory_core()
        memory_core.status = final_status
        memory_id = runtime.add_memory(memory_core)

        if memory_id != memory.retention_id:
            strengthened = self._reinforce_existing(memory_id, observed_at=event.occurred_at)
            self._maybe_send_strengthened_card(strengthened)
            return DomainIngestResult(memory_ids=[memory_id], candidate_count=1, message="team_retention reinforced")

        self.team_retention_store.insert_memory(memory)

        if memory.overwrite_of:
            self.version_manager.apply_supersede(memory.overwrite_of, memory_id)

        if final_status == "active":
            self.team_retention_store.create_review_schedule(memory)

        self.embedding_indexer.upsert(memory, status=final_status)

        self._maybe_send_ingest_card(memory, final_status)

        return DomainIngestResult(
            memory_ids=[memory_id],
            candidate_count=1,
            message=f"team_retention {final_status}: {admission.reason}",
        )

    def _maybe_send_ingest_card(self, memory: TeamRetentionMemory, status: str) -> None:
        if self.notifier is None or not self.chat_id:
            return
        suggestion = self._build_ingest_suggestion(memory, status=status)
        if not suggestion:
            return
        try:
            if status == "active":
                self.notifier.send_team_memory_created(self.chat_id, suggestion)
            elif status == "candidate":
                self.notifier.send_candidate_confirmation(self.chat_id, suggestion)
        except Exception:
            logger.warning(
                "action=ingest_card_failed memory_id=%s status=%s",
                memory.retention_id,
                status,
                exc_info=True,
            )

    def _maybe_send_strengthened_card(self, memory: TeamRetentionMemory) -> None:
        if self.notifier is None or not self.chat_id:
            return
        suggestion = self._build_ingest_suggestion(memory, status="active")
        if not suggestion:
            return
        try:
            self.notifier.send_team_memory_strengthened(self.chat_id, suggestion)
        except Exception:
            logger.warning(
                "action=strengthened_card_failed memory_id=%s",
                memory.retention_id,
                exc_info=True,
            )

    def _build_ingest_suggestion(self, memory: TeamRetentionMemory, *, status: str) -> dict[str, Any] | None:
        row = self.memory_store.get_memory(memory.retention_id)
        if row is None:
            return None
        due_at = memory.next_review_at
        if status == "active" and not due_at:
            due_at = self.team_retention_store.next_review_time(
                memory.created_at or utc_now_iso(),
                review_count=memory.review_count,
                risk_level=memory.risk_level,
                review_policy=memory.review_policy,
            )
        return {
            "memory_id": memory.retention_id,
            "content": memory.fact_value,
            "due_at": due_at,
            "metadata": {
                "risk_level": memory.risk_level,
                "fact_type": memory.fact_type,
            },
        }

    # ------------------------------------------------------------------
    # Rule fallback path
    # ------------------------------------------------------------------

    def _ingest_event_with_rules(self, event: NormalizedEvent, runtime: DomainRuntime) -> DomainIngestResult:
        preprocess = self.preprocessor.preprocess(event)
        if _is_retrieval_question(preprocess.raw_text):
            return DomainIngestResult(candidate_count=0, message="team_retention query skipped")
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

    def _reinforce_existing(self, memory_id: str, *, observed_at: str | None = None) -> TeamRetentionMemory:
        existing = self.team_retention_store.get_memory(memory_id)
        if existing is None:
            raise ValueError(f"team retention memory not found: {memory_id}")
        if self.team_retention_store.get_review_schedule(memory_id) is not None:
            next_review_at = self.team_retention_store.reinforce_review(memory_id, observed_at=observed_at)
            existing.next_review_at = next_review_at
            existing.last_review_at = observed_at
            existing.review_count += 1
            return existing
        next_review_at = self.team_retention_store.reinforce_memory_without_schedule(
            memory_id,
            observed_at=observed_at,
        )
        metadata = dict(existing.metadata)
        metadata["reinforce_count"] = int(metadata.get("reinforce_count") or 0) + 1
        if observed_at is not None:
            metadata["last_reinforced_at"] = observed_at
        self.team_retention_store.update_memory_metadata(memory_id, metadata)
        existing.metadata = metadata
        existing.next_review_at = next_review_at
        existing.last_review_at = observed_at
        existing.review_count += 1
        return existing

    def _find_duplicate(
        self,
        memory: TeamRetentionMemory,
        *,
        allowed_statuses: set[str] | None = None,
    ) -> str | None:
        if not memory.version_group:
            exact_candidates = []
        else:
            exact_candidates = self.team_retention_store.list_memories(
                team_id=memory.team_id,
                project_id=memory.project_id,
                workspace_id=memory.workspace_id,
                fact_type=memory.fact_type,
                version_group=memory.version_group,
                limit=20,
            )
        statuses = allowed_statuses or {"active"}
        existing = list(exact_candidates)
        fuzzy_candidates = self.team_retention_store.list_memories(
            team_id=memory.team_id,
            project_id=memory.project_id,
            workspace_id=memory.workspace_id,
            fact_type=memory.fact_type,
            limit=100,
        )
        seen_ids = {item.retention_id for item in existing}
        existing.extend(item for item in fuzzy_candidates if item.retention_id not in seen_ids)
        for item in existing:
            if item.fact_value.strip() == memory.fact_value.strip():
                row = self.memory_store.get_memory(item.retention_id)
                if row is not None and row.get("status") in statuses:
                    return item.retention_id
        return None

    def _detect_structured_conflict(self, memory: TeamRetentionMemory) -> tuple[TeamRetentionMemory, str] | None:
        rows = self.memory_store.list_active_memories(domain=self.domain, limit=100)
        for row in rows:
            old_memory = self.team_retention_store.get_memory(str(row["memory_id"]))
            if old_memory is None:
                old_memory = TeamRetentionMemory.from_memory_core(row)  # type: ignore[arg-type]
            if old_memory.retention_id == memory.retention_id:
                continue
            if not _same_scope(old_memory, memory):
                continue
            if not _related_fact_type(old_memory.fact_type, memory.fact_type):
                continue
            if not _same_primary_entity(old_memory, memory):
                continue
            reason = _format_conflict_reason(old_memory.fact_value, memory.fact_value)
            if reason:
                return old_memory, reason
        return None

    # ------------------------------------------------------------------
    # Retrieval, update, proactive
    # ------------------------------------------------------------------

    def retrieve(self, query: RetrievalQuery, *, top_k: int) -> list[RankedMemory]:
        results = self.retriever.retrieve(query, limit=top_k)
        return [result.to_ranked_memory(rank=index + 1) for index, result in enumerate(results)]

    def update_memory(self, action: str, **kwargs: Any) -> DomainUpdateResult | None:
        memory_id = kwargs.get("memory_id")
        if action == "acknowledge":
            return DomainUpdateResult(
                action=action,
                memory_id=memory_id,
                updated=True,
                message="acknowledged",
            )
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
        if action == "promote_to_active":
            if memory_id is None:
                raise ValueError("memory_id is required")
            self.memory_store.update_memory_status(memory_id, "active")
            memory = self.team_retention_store.get_memory(memory_id)
            if memory is not None:
                self.team_retention_store.create_review_schedule(memory)
                self._maybe_send_ingest_card(memory, "active")
            return DomainUpdateResult(
                action=action,
                memory_id=memory_id,
                updated=True,
                message="promoted to active with review schedule",
            )
        if action == "dismiss_candidate":
            if memory_id is None:
                raise ValueError("memory_id is required")
            self.memory_store.update_memory_status(memory_id, "forgotten")
            return DomainUpdateResult(
                action=action,
                memory_id=memory_id,
                updated=True,
                message="candidate dismissed",
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


_QUESTION_MARKERS = (
    "什么",
    "应该",
    "怎么",
    "如何",
    "是否",
    "吗",
    "么",
    "?",
    "？",
)
_TEACHING_MARKERS = (
    "请记住",
    "团队记住",
    "长期记住",
    "请记录",
    "创建团队知识",
    "创建记忆",
    "更新团队记忆",
    "更新记忆",
    "已变更",
    "现在必须",
    "以后必须",
    "改为",
    "不再",
)
_UPDATE_MARKERS = (
    "更新",
    "变更",
    "已变更",
    "改为",
    "现在必须",
    "现在使用",
    "以后使用",
    "以后必须",
    "不再",
    "旧规则",
    "废弃",
    "替换",
    "覆盖",
)
_FORMAT_RE = re.compile(r"\b(xlsx|csv|parquet|json|excel)\b", re.IGNORECASE)


def _is_retrieval_question(text: str) -> bool:
    """Return whether a chat message is asking memory instead of teaching memory."""
    cleaned = clean_text(text)
    if not cleaned:
        return False
    if any(marker in cleaned for marker in _TEACHING_MARKERS):
        return False
    return any(marker in cleaned for marker in _QUESTION_MARKERS)


def _has_explicit_update_signal(text: str) -> bool:
    """Return whether text explicitly says a retained fact is being replaced."""
    cleaned = clean_text(text)
    return any(marker in cleaned for marker in _UPDATE_MARKERS)


def _same_scope(left: TeamRetentionMemory, right: TeamRetentionMemory) -> bool:
    """Match retained facts only inside the same available team/project/workspace scope."""
    for field_name in ("team_id", "project_id", "workspace_id"):
        left_value = getattr(left, field_name)
        right_value = getattr(right, field_name)
        if left_value or right_value:
            if not left_value or not right_value or left_value != right_value:
                return False
    return bool(left.team_id or left.project_id or left.workspace_id or right.team_id or right.project_id or right.workspace_id)


def _related_fact_type(left: str, right: str) -> bool:
    """Treat customer/compliance/team facts as related when entity and slot also match."""
    if left == right:
        return True
    related = {"customer_preference", "compliance", "team_fact", "risk"}
    return left in related and right in related


def _same_primary_entity(left: TeamRetentionMemory, right: TeamRetentionMemory) -> bool:
    """Compare primary_entity metadata and customer names with tolerant normalized keys."""
    left_entities = _entity_keys(left)
    right_entities = _entity_keys(right)
    if left_entities and right_entities:
        for left_entity in left_entities:
            for right_entity in right_entities:
                if (
                    left_entity == right_entity
                    or left_entity in right_entity
                    or right_entity in left_entity
                ):
                    return True
    return False


def _entity_keys(memory: TeamRetentionMemory) -> set[str]:
    keys: set[str] = set()
    primary = memory.metadata.get("primary_entity") if memory.metadata else None
    if isinstance(primary, dict):
        for field_name in ("normalized_key", "name"):
            value = primary.get(field_name)
            if isinstance(value, str) and value.strip():
                keys.add(_normalize_entity(value))
                extracted = _extract_customer_key(value)
                if extracted:
                    keys.add(extracted)
    extracted_from_fact = _extract_customer_key(memory.fact_value)
    if extracted_from_fact:
        keys.add(extracted_from_fact)
    return {key for key in keys if key}


def _extract_customer_key(text: str) -> str | None:
    cleaned = clean_text(text)
    match = re.search(r"([\u4e00-\u9fffA-Za-z0-9_-]{1,20})客户", cleaned)
    if match:
        return _normalize_entity(match.group(1))
    match = re.search(r"客户\s*([\u4e00-\u9fffA-Za-z0-9_-]{1,20})", cleaned)
    if match:
        return _normalize_entity(match.group(1))
    return None


def _normalize_entity(value: str) -> str:
    normalized = clean_text(value).lower()
    normalized = normalized.replace("customer-", "")
    normalized = normalized.replace("-customer", "")
    normalized = normalized.replace("customer_", "")
    normalized = normalized.replace("_customer", "")
    normalized = normalized.replace("客户", "")
    normalized = re.sub(r"[\s_-]+", "", normalized)
    return normalized


def _format_conflict_reason(old_value: str, new_value: str) -> str | None:
    if not _same_export_format_slot(old_value, new_value):
        return None
    old_allowed = _accepted_formats(old_value)
    old_rejected = _rejected_formats(old_value)
    new_allowed = _accepted_formats(new_value)
    new_rejected = _rejected_formats(new_value)
    if new_allowed & old_rejected:
        return f"new_allowed_old_rejected:{','.join(sorted(new_allowed & old_rejected))}"
    if old_allowed & new_rejected:
        return f"old_allowed_new_rejected:{','.join(sorted(old_allowed & new_rejected))}"
    if old_allowed and new_allowed and old_allowed.isdisjoint(new_allowed):
        return f"format_changed:{','.join(sorted(old_allowed))}->{','.join(sorted(new_allowed))}"
    return None


def _same_export_format_slot(left: str, right: str) -> bool:
    left_cleaned = clean_text(left)
    right_cleaned = clean_text(right)
    slot_markers = ("导出", "格式", "生产数据")
    return any(marker in left_cleaned for marker in slot_markers) and any(marker in right_cleaned for marker in slot_markers)


def _accepted_formats(text: str) -> set[str]:
    allowed = _formats_near_markers(text, ("必须使用", "要求", "使用", "接受", "改为", "现在必须", "现在使用"))
    cleaned = clean_text(text).lower()
    if not allowed and any(marker in cleaned for marker in ("使用", "要求", "必须", "接受")):
        allowed.update(match.group(1).lower() for match in _FORMAT_RE.finditer(cleaned))
    return allowed - _rejected_formats(text)


def _rejected_formats(text: str) -> set[str]:
    rejected = _formats_near_markers(text, ("不接受", "不再使用", "不允许", "禁止", "不要", "不用", "不行"))
    cleaned = clean_text(text).lower()
    for match in re.finditer(r"\b(xlsx|csv|parquet|json|excel)\b[，,、\s]{0,3}不行", cleaned):
        rejected.add(match.group(1).lower())
    return rejected


def _formats_near_markers(text: str, markers: tuple[str, ...]) -> set[str]:
    cleaned = clean_text(text).lower()
    formats: set[str] = set()
    for marker in markers:
        start = 0
        while True:
            index = cleaned.find(marker.lower(), start)
            if index < 0:
                break
            window = cleaned[index:index + 24]
            formats.update(match.group(1).lower() for match in _FORMAT_RE.finditer(window))
            start = index + len(marker)
    return formats
