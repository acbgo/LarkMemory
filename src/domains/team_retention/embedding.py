from __future__ import annotations

from typing import Any

from src.storage import EmbeddingStore

from .models import TeamRetentionMemory


class TeamRetentionEmbeddingIndexer:
    """Build and maintain the side vector index for team_retention memories."""

    def __init__(self, embedding_store: EmbeddingStore | None) -> None:
        self.embedding_store = embedding_store

    def enabled(self) -> bool:
        """Return whether an embedding store is available for indexing/search."""
        return self.embedding_store is not None

    def upsert(self, memory: TeamRetentionMemory, *, status: str) -> None:
        """Index one candidate or active team retention memory by memory_id."""
        if self.embedding_store is None:
            return
        self.embedding_store.upsert_embedding(
            memory_id=memory.retention_id,
            text=self.build_text(memory),
            metadata=self.build_metadata(memory, status=status),
        )

    def query_similar(self, memory: TeamRetentionMemory, *, top_k: int = 10) -> list[dict[str, Any]]:
        """Return vector hits scoped to team_retention for lifecycle comparison."""
        if self.embedding_store is None:
            return []
        filters: dict[str, Any] = {}
        if memory.team_id:
            filters["team_id"] = memory.team_id
        if memory.project_id:
            filters["project_id"] = memory.project_id
        if memory.workspace_id:
            filters["workspace_id"] = memory.workspace_id
        return self.embedding_store.query_similar(
            self.build_text(memory),
            domain="team_retention",
            top_k=top_k,
            filters=filters,
        )

    def build_text(self, memory: TeamRetentionMemory) -> str:
        """Build stable text for semantic indexing and lifecycle search."""
        return "\n".join(
            part
            for part in (
                f"类型: {memory.fact_type}",
                f"事实: {memory.fact_value}",
                f"风险: {memory.risk_level}",
                f"负责人: {memory.owner}" if memory.owner else "",
                f"范围: team={memory.team_id} project={memory.project_id} workspace={memory.workspace_id}",
                f"版本组: {memory.version_group}" if memory.version_group else "",
            )
            if part
        )

    def build_metadata(self, memory: TeamRetentionMemory, *, status: str) -> dict[str, Any]:
        """Build metadata used to scope vector retrieval and refresh status."""
        metadata = {
            "memory_id": memory.retention_id,
            "domain": "team_retention",
            "status": status,
            "team_id": memory.team_id,
            "project_id": memory.project_id,
            "workspace_id": memory.workspace_id,
            "fact_type": memory.fact_type,
            "risk_level": memory.risk_level,
            "version_group": memory.version_group,
        }
        return {key: value for key, value in metadata.items() if value is not None}
