from __future__ import annotations

import logging
from typing import Any

from src.llm import EmbeddingClient
from src.storage import EmbeddingStore

from .models import ProjectDecision


logger = logging.getLogger(__name__)


class ProjectDecisionEmbeddingIndexer:
    """维护 project_decision 领域记忆的旁路向量索引。"""

    def __init__(
        self,
        embedding_store: EmbeddingStore | None,
        embedding_client: EmbeddingClient | None = None,
    ) -> None:
        self.embedding_store = embedding_store
        self.embedding_client = embedding_client

    def enabled(self) -> bool:
        """返回当前是否具备向量索引写入能力。"""
        return self.embedding_store is not None

    def upsert(self, decision: ProjectDecision, *, status: str) -> None:
        """将单条项目决策写入向量索引，失败只记录日志不阻断入库。"""
        if self.embedding_store is None:
            logger.info(
                "action=embedding_index_skipped reason=store_unavailable memory_id=%s domain=project_decision",
                decision.decision_id,
            )
            return
        text = self.build_text(decision)
        metadata = self.build_metadata(decision, status=status)
        logger.info(
            "action=embedding_payload_built memory_id=%s domain=project_decision text_length=%s metadata_count=%s",
            decision.decision_id,
            len(text),
            len(metadata),
        )
        embedding = None
        if self.embedding_client is not None:
            try:
                embedding = self.embedding_client.embed_text(text)
                logger.info(
                    "action=embedding_vector_done memory_id=%s domain=project_decision embedding_dim=%s",
                    decision.decision_id,
                    len(embedding),
                )
            except Exception:
                logger.warning(
                    "action=embedding_vector_failed memory_id=%s domain=project_decision",
                    decision.decision_id,
                    exc_info=True,
                )
                return
        try:
            self.embedding_store.upsert_embedding(
                memory_id=decision.decision_id,
                text=text,
                metadata=metadata,
                embedding=embedding,
            )
            logger.info(
                "action=embedding_indexed memory_id=%s domain=project_decision has_embedding=%s",
                decision.decision_id,
                embedding is not None,
            )
        except Exception:
            logger.warning(
                "action=embedding_index_failed memory_id=%s domain=project_decision",
                decision.decision_id,
                exc_info=True,
            )

    def build_text(self, decision: ProjectDecision) -> str:
        """构造稳定的语义索引文本，覆盖决策主题、结论、依据和范围。"""
        return "\n".join(
            part
            for part in (
                f"主题: {decision.topic}",
                f"结论: {decision.decision}",
                f"完整结论: {decision.conclusion}" if decision.conclusion else "",
                "理由: " + "；".join(decision.reasons) if decision.reasons else "",
                "反对意见: " + "；".join(decision.objections) if decision.objections else "",
                "备选方案: " + "；".join(decision.alternatives) if decision.alternatives else "",
                f"阶段: {decision.stage}" if decision.stage else "",
                (
                    "范围: "
                    f"project={decision.project_id} "
                    f"team={decision.team_id} "
                    f"workspace={decision.workspace_id}"
                ),
                f"来源: {decision.source_ref}" if decision.source_ref else "",
            )
            if part
        )

    def build_metadata(self, decision: ProjectDecision, *, status: str) -> dict[str, Any]:
        """构造向量检索过滤用 metadata，并过滤空值。"""
        metadata = {
            "memory_id": decision.decision_id,
            "domain": "project_decision",
            "status": status,
            "project_id": decision.project_id,
            "team_id": decision.team_id,
            "workspace_id": decision.workspace_id,
            "topic": decision.topic,
            "stage": decision.stage,
            "source_ref": decision.source_ref,
        }
        return {key: value for key, value in metadata.items() if value is not None}
