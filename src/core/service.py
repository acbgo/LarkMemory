from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field, replace
from typing import Any, Iterable

from src.core.access_tracker import AccessTracker
from src.core.admission_control import AdmissionController
from src.core.decay import DecayPolicy
from src.core.dedup_merge import DedupMergeEngine
from src.core.domain_classifier import DomainClassifier
from src.core.domain_handler import DomainRuntime, MemoryDomainHandler
from src.core.router import DomainRouter
from src.core.scheduler import ScheduledTaskResult, Scheduler
from src.core.supersede import SupersedeManager
from src.proactive import ProactiveEngine
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
from src.llm import EmbeddingClient, RerankClient
from src.utils.ids import query_id as new_query_id


logger = logging.getLogger(__name__)


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
        embedding_client: EmbeddingClient | None = None,
        rerank_client: RerankClient | None = None,
        llm_client: Any | None = None,
        router: DomainRouter | None = None,
        admission: AdmissionController | None = None,
        dedup: DedupMergeEngine | None = None,
        supersede: SupersedeManager | None = None,
        decay_policy: DecayPolicy | None = None,
        access_tracker: AccessTracker | None = None,
        domain_handlers: Iterable[MemoryDomainHandler] | None = None,
        proactive_engine: ProactiveEngine | None = None,
    ) -> None:
        self.event_store = event_store
        self.memory_store = memory_store
        self.embedding_store = embedding_store
        self.embedding_client = embedding_client
        self.rerank_client = rerank_client
        self.llm_client = llm_client
        self.classifier = DomainClassifier(llm_client=llm_client)
        self.router = router or DomainRouter(classifier=self.classifier)
        self.admission = admission or AdmissionController(llm_client=llm_client)
        if admission is not None and getattr(admission, "llm_client", None) is None:
            admission.llm_client = llm_client
        self.dedup = dedup or DedupMergeEngine()
        self.supersede = supersede or SupersedeManager(memory_store)
        self.decay_policy = decay_policy or DecayPolicy()
        self.access_tracker = access_tracker or AccessTracker()
        self.domain_handlers = {
            handler.domain: handler
            for handler in (domain_handlers or [])
        }
        self.proactive_engine = proactive_engine
        self.rerank_client = rerank_client

    def ingest_event(self, event: NormalizedEvent) -> IngestResult:
        logger.info(
            "action=start event_id=%s event_type=%s source_type=%s",
            event.event_id,
            event.event_type,
            event.source_type,
        )
        # 先存一份原始事件
        event_id = self.event_store.insert_event(event)
        # LLM 做路由
        route_decision = self.router.route_event(event)
        primary_domain = route_decision.primary[0].domain if route_decision.primary else None
        # 决定要不要抽取长期记忆
        # TODO：这里是不是应该先做判断再路由？
        event_admission = self.admission.evaluate_event(event, domain=primary_domain)
        if not event_admission.admitted:
            logger.info(
                "action=event_admission_rejected event_id=%s reason=%s",
                event.event_id,
                event_admission.reason,
            )
            return IngestResult(
                event_id=event_id,
                stored=True,
                message=f"event stored; admission rejected: {event_admission.reason}",
            )
        handler = self.domain_handlers.get(primary_domain or "")
        if handler is None:
            return IngestResult(
                event_id=event_id,
                stored=True,
                message="event stored; no domain handler registered",
            )

        runtime = DomainRuntime(
            memory_store=self.memory_store,
            add_memory=self.add_memory,
            embedding_store=self.embedding_store,
            embedding_client=self.embedding_client,
        )
        domain_result = handler.ingest_event(event, runtime)
        if self.proactive_engine is not None:
            try:
                self.proactive_engine.maybe_push(
                    event,
                    domain=primary_domain,
                    memory_ids=domain_result.memory_ids,
                )
            except Exception:
                logger.warning(
                    "action=proactive_engine_failed event_id=%s domain=%s",
                    event.event_id,
                    primary_domain,
                    exc_info=True,
                )
        return IngestResult(
            event_id=event_id,
            stored=True,
            memory_ids=domain_result.memory_ids,
            candidate_count=domain_result.candidate_count,
            message=f"event stored; {domain_result.message or primary_domain}",
        )

    def add_memory(self, memory: MemoryCore) -> str:
        admission = self.admission.evaluate_memory(memory)
        if not admission.admitted:
            raise ValueError(f"memory rejected: {admission.reason}")
        if memory.overwrite_of:
            logger.info(
                "action=dedup_skipped reason=overwrite_of memory_id=%s overwrite_of=%s",
                memory.memory_id,
                memory.overwrite_of,
            )
            return self.memory_store.insert_memory_core(memory)
        existing = [
            *self.memory_store.search_memory_candidates(domain=memory.domain, status="active"),
            *self.memory_store.search_memory_candidates(domain=memory.domain, status="candidate"),
        ]
        scoped_existing = self._filter_dedup_candidates_by_scope(memory, existing)
        duplicate = self.dedup.find_duplicate(memory, scoped_existing)
        if duplicate.duplicate_found and duplicate.matched_memory_id:
            logger.info(
                "action=dedup_matched memory_id=%s matched_memory_id=%s score=%s reason=%s",
                memory.memory_id,
                duplicate.matched_memory_id,
                duplicate.score,
                duplicate.reason,
            )
            return duplicate.matched_memory_id
        return self.memory_store.insert_memory_core(memory)

    def retrieve(
        self,
        query: RetrievalQuery,
        *,
        top_k: int = 10,
        include_trace: bool = False,
    ) -> RetrieveResult:
        """Run retrieval from synchronous callers such as CLI scripts and sync unit tests."""
        return _run_async(self.retrieve_async(query, top_k=top_k, include_trace=include_trace))

    async def retrieve_async(
        self,
        query: RetrievalQuery,
        *,
        top_k: int = 10,
        include_trace: bool = False,
    ) -> RetrieveResult:
        """Run the retrieval pipeline inside an existing async runtime without nesting event loops."""
        if top_k < 1:
            raise ValueError("top_k must be greater than 0")
        query_id = new_query_id()
        logger.info(
            "action=retrieve_start query_id=%s query_text=%s top_k=%s include_trace=%s",
            query_id,
            query.query_text,
            top_k,
            include_trace,
        )
        intent = await IntentAnalyzer(classifier=self.classifier).analyze(query)
        logger.info(
            "action=intent_analyzed query_text=%s primary_domains=%s secondary_domains=%s intent_type=%s confidence=%s keyword_count=%s",
            query.query_text,
            [domain.value for domain in intent.primary_domains],
            [domain.value for domain in intent.secondary_domains],
            intent.intent_type,
            intent.confidence,
            len(intent.keywords),
        )
        rewritten = await QueryRewriter(self.llm_client).rewrite(query, intent)
        logger.info(
            "action=query_rewritten query_text=%s rewritten_text=%s variant_count=%s",
            query.query_text,
            rewritten.rewritten_text,
            len(rewritten.query_variants or []),
        )
        primary_domains = [
            domain.value
            for domain in intent.primary_domains
            if domain.value in self.domain_handlers
        ]
        secondary_domains = [
            domain.value
            for domain in intent.secondary_domains
            if domain.value in self.domain_handlers and domain.value not in primary_domains
        ]

        domain_ranked: list[tuple[str, RankedMemory]] = []
        handler_query = self._with_rewritten_context(query, rewritten)
        target_domains: list[str] = []
        for domain in primary_domains:
            target_domains.append(domain)
            for ranked in self.domain_handlers[domain].retrieve(handler_query, top_k=top_k):
                domain_ranked.append((domain, ranked))
        if not domain_ranked:
            for domain in secondary_domains:
                target_domains.append(domain)
                for ranked in self.domain_handlers[domain].retrieve(handler_query, top_k=top_k):
                    domain_ranked.append((domain, ranked))
        logger.info(
            "action=domain_retrieve_done query_id=%s target_domains=%s candidate_count=%s",
            query_id,
            target_domains,
            len(domain_ranked),
        )

        if domain_ranked:
            candidates = [
                FusedCandidate(
                    item=ranked.item,
                    source_domain=ranked.item.domain,
                    domain_rank=ranked.rank or index + 1,
                    fusion_score=max(ranked.final_score, 0.01),
                )
                for index, (_domain, ranked) in enumerate(domain_ranked)
            ]
            ranked = await Reranker(rerank_client=self.rerank_client).rerank(
                candidates,
                rewritten,
                top_k=top_k,
            )
            for result in ranked:
                self.access_tracker.record_access(result.item.memory_id, query_id=query_id)
            trace = None
            if include_trace:
                trace = {
                    "mode": "domain_handlers",
                    "target_domains": target_domains,
                    "candidate_count": len(candidates),
                    "result_count": len(ranked),
                }
            return RetrieveResult(
                query_id=query_id,
                ranked_memories=ranked,
                trace=trace,
                message="domain handler retrieval",
            )

        rows = self._filter_rows_by_query_scope(
            self.memory_store.list_active_memories(limit=max(top_k * 5, 20)),
            query,
        )
        logger.info(
            "action=memory_core_fallback_loaded query_id=%s row_count=%s",
            query_id,
            len(rows),
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
        ranked = await Reranker(rerank_client=self.rerank_client).rerank(
            candidates,
            rewritten,
            top_k=top_k,
        )
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
            message="memory_core fallback; no domain handler results",
        )

    async def _rerank_candidates(
        self,
        candidates: list[FusedCandidate],
        query: Any,
        *,
        top_k: int,
    ) -> list[RankedMemory]:
        """用全局 rerank provider 重排候选；不可用时回退到本地多因子排序。"""
        if self.rerank_client is None or len(candidates) <= 1:
            logger.info(
                "action=global_rerank_skipped reason=%s candidate_count=%s top_k=%s",
                "client_unavailable" if self.rerank_client is None else "single_candidate",
                len(candidates),
                top_k,
            )
            return await Reranker(llm_client=None).rerank(candidates, query, top_k=top_k)
        documents = [
            RerankDocument(
                id=candidate.item.memory_id,
                text=self._build_global_rerank_text(candidate),
                metadata={
                    "domain": candidate.item.domain,
                    "fusion_score": candidate.fusion_score,
                },
            )
            for candidate in candidates
        ]
        try:
            response = self.rerank_client.rerank(query.rewritten_text or query.original.query_text, documents, top_k=top_k)
        except Exception:
            logger.warning(
                "action=global_rerank_failed candidate_count=%s top_k=%s",
                len(candidates),
                top_k,
                exc_info=True,
            )
            return await Reranker(llm_client=None).rerank(candidates, query, top_k=top_k)

        candidate_by_id = {candidate.item.memory_id: candidate for candidate in candidates}
        scores = [float(result.score) for result in response.results]
        if scores and all(score == 0.0 for score in scores):
            logger.warning(
                "action=global_rerank_zero_scores candidate_count=%s result_count=%s top_k=%s fallback=local_reranker raw_scores=%s",
                len(candidates),
                len(response.results),
                top_k,
                [(result.id, float(result.score)) for result in response.results[:top_k]],
            )
            return await Reranker(llm_client=None).rerank(candidates, query, top_k=top_k)
        score_min = min(scores) if scores else 0.0
        score_max = max(scores) if scores else 1.0
        score_range = score_max - score_min or 1.0
        ranked: list[RankedMemory] = []
        for index, result in enumerate(response.results[:top_k], start=1):
            candidate = candidate_by_id.get(result.id)
            if candidate is None:
                continue
            raw_score = float(result.score)
            normalized_score = (raw_score - score_min) / score_range
            ranked.append(
                RankedMemory(
                    item=candidate.item,
                    final_score=normalized_score,
                    rank=index,
                    score_breakdown={
                        "global_rerank": normalized_score,
                        "global_rerank_raw": raw_score,
                        "fusion": candidate.fusion_score,
                    },
                )
            )
        logger.info(
            "action=global_rerank_done model=%s candidate_count=%s result_count=%s top_k=%s top_ids=%s raw_scores=%s normalized_scores=%s",
            getattr(response, "model", None),
            len(candidates),
            len(response.results),
            top_k,
            [item.item.memory_id for item in ranked],
            [(result.id, float(result.score)) for result in response.results[:top_k]],
            [(item.item.memory_id, item.final_score) for item in ranked],
        )
        return ranked

    def _build_global_rerank_text(self, candidate: FusedCandidate) -> str:
        """为跨域 rerank 构造简洁、带 domain 的候选文本。"""
        item = candidate.item
        return "\n".join(
            part
            for part in (
                f"domain={item.domain}",
                f"summary={item.summary_text or ''}",
                f"content={item.content_text or ''}",
                f"tags={' '.join(item.tags)}",
                f"entities={' '.join(item.entities)}",
            )
            if part
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
        kwargs = {
            "memory_id": memory_id,
            "new_memory_id": new_memory_id,
            "confidence": confidence,
            "importance": importance,
            "feedback_signal": feedback_signal,
            "reviewed_at": reviewed_at,
            "snooze_days": snooze_days,
        }
        for handler in self.domain_handlers.values():
            domain_result = handler.update_memory(action, **kwargs)
            if domain_result is not None:
                if action == "reviewed" and memory_id is not None:
                    self.access_tracker.record_feedback(memory_id, feedback_signal or "reviewed")
                return UpdateResult(
                    action=domain_result.action,
                    memory_id=domain_result.memory_id,
                    updated=domain_result.updated,
                    message=domain_result.message,
                )

        if action in {"expire", "forget"}:
            if memory_id is None:
                raise ValueError("memory_id is required")
            self._require_memory_exists(memory_id)
            self.memory_store.update_memory_status(memory_id, "expired" if action == "expire" else "forgotten")
            self._notify_domain_update(action, **kwargs)
            return UpdateResult(action=action, memory_id=memory_id, updated=True)
        if action == "supersede":
            if memory_id is None or new_memory_id is None:
                raise ValueError("memory_id and new_memory_id are required")
            self._require_memory_exists(memory_id)
            self._require_memory_exists(new_memory_id)
            self.supersede.mark_superseded(memory_id, new_memory_id)
            self._notify_domain_update(action, **kwargs)
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
        suggestions: list[dict[str, Any]] = []
        for handler in self.domain_handlers.values():
            suggestions.extend(
                handler.proactive_suggestions(
                    user_id=user_id,
                    project_id=project_id,
                    team_id=team_id,
                    workspace_id=workspace_id,
                    limit=limit,
                    now=now,
                    warning_window_hours=warning_window_hours,
                )
            )
        return suggestions[:limit]

    def run_maintenance(self) -> dict[str, ScheduledTaskResult]:
        result = Scheduler(self.memory_store, self.decay_policy).run_once()
        review = result.setdefault("review_due", ScheduledTaskResult(task_name="review_due"))
        for handler in self.domain_handlers.values():
            suggestions = handler.scan_review_due(limit=100)
            review.scanned += len(suggestions)
            review.suggestions.extend(suggestions)
        return result

    def _notify_domain_update(self, action: str, **kwargs: Any) -> None:
        for handler in self.domain_handlers.values():
            handler.update_memory(action, **kwargs)

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

    def _with_rewritten_context(self, query: RetrievalQuery, rewritten: Any) -> RetrievalQuery:
        """将改写查询信号放入 session_context，供领域 retriever 选择性消费。"""
        context = dict(query.session_context)
        context["rewritten_text"] = rewritten.rewritten_text
        context["query_variants"] = list(rewritten.query_variants or [query.query_text])
        return replace(query, session_context=context)

    def _filter_dedup_candidates_by_scope(
        self,
        memory: MemoryCore,
        rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """按 MemoryCore entities 中的 scope 标记过滤去重候选，避免跨项目/团队误去重。"""
        scope = self._memory_scope_markers(memory)
        if not scope:
            return rows
        result: list[dict[str, Any]] = []
        for row in rows:
            row_scope = self._row_scope_markers(row)
            if all(row_scope.get(key) == value for key, value in scope.items()):
                result.append(row)
        return result

    def _memory_scope_markers(self, memory: MemoryCore) -> dict[str, str]:
        """从 MemoryCore entities 中提取 project/team/workspace/user 维度的去重 scope。"""
        return self._scope_markers_from_entities(memory.entities)

    def _row_scope_markers(self, row: dict[str, Any]) -> dict[str, str]:
        """从 store 行的 entities 字段中提取去重 scope。"""
        return self._scope_markers_from_entities(list(row.get("entities") or row.get("entities_json") or []))

    def _scope_markers_from_entities(self, entities: list[str]) -> dict[str, str]:
        """解析 `key:value` 形式的 scope 标记，只保留去重相关维度。"""
        allowed = {"project_id", "team_id", "workspace_id", "user_id"}
        result: dict[str, str] = {}
        for entity in entities:
            if not isinstance(entity, str) or ":" not in entity:
                continue
            key, value = entity.split(":", 1)
            if key in allowed and value:
                result[key] = value
        return result

    def _row_has_scope(self, terms: list[str], key: str, value: str) -> bool:
        return value in terms or f"{key}:{value}" in terms


def _run_async(awaitable: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    else:
        raise RuntimeError("MemoryService sync API cannot run inside an active event loop")

