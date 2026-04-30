from __future__ import annotations

from dataclasses import dataclass

from src.storage import MemoryCoreStore, TeamRetentionStore

from .embedding import TeamRetentionEmbeddingIndexer
from .models import TeamRetentionMemory


@dataclass(slots=True)
class TeamRetentionLifecycleDecision:
    action: str = "new"
    status: str | None = None
    matched_memory_id: str | None = None
    reason: str = ""


class TeamRetentionLifecycleResolver:
    """Resolve similar team memories before insert using DB and vector candidates."""

    def __init__(
        self,
        memory_store: MemoryCoreStore,
        team_store: TeamRetentionStore,
        embedding_indexer: TeamRetentionEmbeddingIndexer,
    ) -> None:
        self.memory_store = memory_store
        self.team_store = team_store
        self.embedding_indexer = embedding_indexer

    def resolve(self, memory: TeamRetentionMemory) -> TeamRetentionLifecycleDecision:
        """Return lifecycle action for a newly extracted memory."""
        candidates = self._candidate_ids_from_db(memory)
        candidates.extend(self._candidate_ids_from_vector(memory))
        seen: set[str] = set()
        for memory_id in candidates:
            if memory_id in seen:
                continue
            seen.add(memory_id)
            old = self.team_store.get_memory(memory_id)
            row = self.memory_store.get_memory(memory_id)
            if old is None or row is None:
                continue
            if row.get("status") not in {"active", "candidate"}:
                continue
            if not self._same_scope(old, memory):
                continue
            if old.fact_type != memory.fact_type:
                continue
            if old.fact_value.strip() == memory.fact_value.strip():
                return TeamRetentionLifecycleDecision(
                    action="reinforce",
                    status=row.get("status") or "candidate",
                    matched_memory_id=memory_id,
                    reason="same_fact_value",
                )
            if self._has_supersede_signal(memory.fact_value):
                return TeamRetentionLifecycleDecision(
                    action="supersede",
                    status="active" if row.get("status") == "active" else "candidate",
                    matched_memory_id=memory_id,
                    reason="explicit_update_signal",
                )
            return TeamRetentionLifecycleDecision(
                action="conflict",
                status="candidate",
                matched_memory_id=memory_id,
                reason="similar_changed_fact_needs_confirmation",
            )
        return TeamRetentionLifecycleDecision(action="new")

    def _candidate_ids_from_db(self, memory: TeamRetentionMemory) -> list[str]:
        if not memory.version_group:
            return []
        return [
            item.retention_id
            for item in self.team_store.list_memories(
                team_id=memory.team_id,
                project_id=memory.project_id,
                workspace_id=memory.workspace_id,
                fact_type=memory.fact_type,
                version_group=memory.version_group,
                limit=20,
            )
        ]

    def _candidate_ids_from_vector(self, memory: TeamRetentionMemory) -> list[str]:
        hits = self.embedding_indexer.query_similar(memory, top_k=10)
        result: list[str] = []
        for hit in hits:
            memory_id = hit.get("memory_id") or hit.get("id")
            if not isinstance(memory_id, str):
                continue
            distance = hit.get("distance")
            if isinstance(distance, (int, float)) and float(distance) > 0.35:
                continue
            result.append(memory_id)
        return result

    def _same_scope(self, left: TeamRetentionMemory, right: TeamRetentionMemory) -> bool:
        for field in ("team_id", "project_id", "workspace_id"):
            left_value = getattr(left, field)
            right_value = getattr(right, field)
            if left_value or right_value:
                if left_value != right_value:
                    return False
        return bool(left.team_id or left.project_id or left.workspace_id or right.team_id or right.project_id or right.workspace_id)

    def _has_supersede_signal(self, text: str) -> bool:
        return any(
            marker in text
            for marker in (
                "现在",
                "改为",
                "更新为",
                "替换",
                "不再",
                "旧",
                "不用",
                "以后按",
            )
        )
