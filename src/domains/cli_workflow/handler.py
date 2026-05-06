from __future__ import annotations

import logging
import json
from typing import Any

from src.core.domain_handler import DomainIngestResult, DomainRuntime, DomainUpdateResult
from src.llm import EmbeddingClient, RerankClient
from src.retrieval import RankedMemory, RetrievalQuery
from src.schemas import NormalizedEvent
from src.storage import CLIWorkflowStore, EmbeddingStore, MemoryCoreStore
from src.storage.cli_workflow_store import extract_parameter_policies, infer_scenario_signature
from src.utils.text import clean_text

from .extractor import CLIWorkflowExtractor
from .retriever import CLIWorkflowRetriever
from .versioning import CLIWorkflowVersionManager


logger = logging.getLogger(__name__)

_POLICY_DECISION_SYSTEM = (
    "你是 CLI 主动参数记忆的写入决策器。"
    "给定用户新输入中抽取出的参数策略，以及检索出的 top1 旧策略，"
    "判断应该执行 ADD、UPDATE、DELETE、NONE。"
    "ADD 表示新增不同场景记忆；UPDATE 表示同一场景同一参数的新值覆盖旧值；"
    "DELETE 表示用户明确要求忘记/删除旧记忆；NONE 表示非教学、重复或不应写入。"
    "只返回 JSON。"
)

_POLICY_DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["operation", "confidence", "reason"],
    "properties": {
        "operation": {"type": "string", "enum": ["ADD", "UPDATE", "DELETE", "NONE"]},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
        "conflict_fields": {"type": "array", "items": {"type": "string"}},
    },
}


class CLIWorkflowDomainHandler:
    domain = "cli_workflow"

    def __init__(
        self,
        memory_store: MemoryCoreStore,
        *,
        llm_client: Any | None = None,
        extractor: CLIWorkflowExtractor | None = None,
        cli_store: CLIWorkflowStore | None = None,
        embedding_store: EmbeddingStore | None = None,
        embedding_client: EmbeddingClient | None = None,
        rerank_client: RerankClient | None = None,
        retriever: CLIWorkflowRetriever | None = None,
        version_manager: CLIWorkflowVersionManager | None = None,
    ) -> None:
        self.memory_store = memory_store
        self.cli_store = cli_store
        self.llm_client = llm_client
        self.embedding_store = embedding_store
        self.embedding_client = embedding_client
        self.extractor = extractor or CLIWorkflowExtractor(llm_client=llm_client, memory_store=memory_store)
        self.retriever = retriever or CLIWorkflowRetriever(
            memory_store,
            cli_store=cli_store,
            llm_client=llm_client,
            embedding_store=embedding_store,
            embedding_client=embedding_client,
            rerank_client=rerank_client,
        )
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
                self._store_cli_embedding(candidate, version_decision.old_memory_id)
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
            self._store_cli_embedding(candidate, memory_id)

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
        text = event.content_text or ""
        policy_items = extract_parameter_policies(text)
        ids: list[str] = []
        for item in policy_items:
            scenario_signature = infer_scenario_signature(text)
            top1 = self.cli_store.find_top_parameter_policy(
                user_id=user_id,
                project_id=event.context.project_id,
                param_name=item["param_name"],
                scenario_signature=scenario_signature,
            )
            operation = self._decide_parameter_policy_operation(
                text=text,
                candidate={
                    "scenario_signature": scenario_signature,
                    "param_name": item["param_name"],
                    "param_value": item["param_value"],
                    "project_id": event.context.project_id,
                },
                existing=top1,
            )
            if operation == "NONE":
                continue
            if operation == "DELETE":
                if top1:
                    self.cli_store.mark_parameter_policy_status(str(top1["policy_id"]), status="forgotten")
                continue
            ids.append(
                self.cli_store.upsert_parameter_policy(
                    scenario_text=text,
                    scenario_signature=scenario_signature,
                    param_name=item["param_name"],
                    param_value=item["param_value"],
                    user_id=user_id,
                    project_id=event.context.project_id,
                    semantic_description=text,
                )
            )
        return ids

    def _decide_parameter_policy_operation(
        self,
        *,
        text: str,
        candidate: dict[str, Any],
        existing: dict[str, Any] | None,
    ) -> str:
        """Ask LLM to judge ADD/UPDATE/DELETE/NONE before writing a parameter policy."""
        if existing is None:
            return "DELETE" if _looks_like_delete_request(text) else "ADD"
        if self.llm_client is None:
            if _looks_like_delete_request(text):
                return "DELETE"
            return "UPDATE" if existing.get("param_value") != candidate.get("param_value") else "NONE"
        try:
            raw = _run_async(
                self.llm_client.ajson(
                    _POLICY_DECISION_SYSTEM,
                    json.dumps(
                        {
                            "user_text": text,
                            "candidate": candidate,
                            "top1_existing": dict(existing),
                        },
                        ensure_ascii=False,
                    ),
                    schema=_POLICY_DECISION_SCHEMA,
                    temperature=0,
                    max_tokens=256,
                )
            )
        except Exception:
            if _looks_like_delete_request(text):
                return "DELETE"
            return "UPDATE" if existing.get("param_value") != candidate.get("param_value") else "NONE"
        operation = str(raw.get("operation") or "").upper()
        confidence = float(raw.get("confidence") or 0.0)
        if operation not in {"ADD", "UPDATE", "DELETE", "NONE"} or confidence < 0.5:
            return "UPDATE" if existing.get("param_value") != candidate.get("param_value") else "NONE"
        return operation

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
            semantic_description=candidate.memory.semantic_description or candidate.evidence_text,
        )

    def _store_cli_embedding(self, candidate: Any, memory_id_value: str) -> None:
        """把 CLI 语义描述写入向量库，供 semantic_description 检索使用。"""
        if self.embedding_store is None or self.embedding_client is None:
            return
        text = clean_text(
            " ".join(
                part
                for part in (
                    candidate.memory.semantic_description,
                    " ".join(candidate.memory.scenario_keywords or []),
                    candidate.memory.command_template,
                )
                if part
            )
        )
        if not text:
            return
        vector = self.embedding_client.embed_text(text)
        self.embedding_store.upsert_embedding(
            memory_id_value,
            text,
            {
                "domain": "cli_workflow",
                "user_id": candidate.memory.user_id,
                "project_id": candidate.memory.project_id or "",
                "command_name": candidate.memory.command_name,
            },
            embedding=vector,
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


def _run_async(awaitable: Any) -> Any:
    """Run async LLM write-decision calls from the sync domain handler."""
    try:
        import asyncio
        asyncio.get_running_loop()
    except RuntimeError:
        import asyncio
        return asyncio.run(awaitable)
    raise RuntimeError("CLIWorkflowDomainHandler sync API cannot run inside an active event loop")


def _looks_like_delete_request(text: str) -> bool:
    """Detect explicit forgetting/deletion wording as a deterministic fallback."""
    lowered = clean_text(text).lower()
    markers = ("忘记", "删除", "不要记", "不用记", "取消记忆", "forget", "delete")
    return any(marker in lowered for marker in markers)
