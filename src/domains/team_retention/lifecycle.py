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

    def resolve(
        self,
        memory: TeamRetentionMemory,
        *,
        admission_status: str = "candidate",
        update_intent: str = "none",
        update_signal_text: str | None = None,
        needs_confirmation: bool = False,
        evidence_text: str | None = None,
        source_text: str | None = None,
    ) -> TeamRetentionLifecycleDecision:
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
            can_supersede = (
                admission_status == "active"
                and not needs_confirmation
                and update_intent in {"none", "conflict", "supersede"}
                and self._same_version_group(old, memory)
                and (
                    (update_intent == "supersede" and bool(update_signal_text))
                    or self._has_supersede_signal(
                        memory.fact_value,
                        evidence_text=evidence_text,
                        source_text=source_text,
                        update_signal_text=update_signal_text,
                    )
                )
            )
            if can_supersede:
                return TeamRetentionLifecycleDecision(
                    action="supersede",
                    status=admission_status,
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

    def _same_version_group(self, left: TeamRetentionMemory, right: TeamRetentionMemory) -> bool:
        """Require exact group or same entity plus same fact slot before supersede."""
        if not left.version_group or not right.version_group:
            return False
        if left.version_group == right.version_group:
            return True
        left_entity, left_slot = self._entity_and_slot(left)
        right_entity, right_slot = self._entity_and_slot(right)
        return bool(
            left_entity
            and right_entity
            and left_entity == right_entity
            and left_slot
            and right_slot
            and left_slot == right_slot
        )

    def _entity_and_slot(self, memory: TeamRetentionMemory) -> tuple[str | None, str | None]:
        """Parse handler-created version groups into entity and fact-slot parts."""
        if not memory.version_group:
            return None, None
        parts = [part for part in memory.version_group.split(":") if part]
        if len(parts) < 4:
            return None, None
        entity = parts[-2]
        slot = parts[-1]
        if entity == "unknown" or slot == "unknown":
            return None, None
        return entity, slot

    def _has_supersede_signal(
        self,
        text: str,
        *,
        update_signal_text: str | None = None,
        evidence_text: str | None = None,
        source_text: str | None = None,
    ) -> bool:
        combined = " ".join(part for part in (text, update_signal_text, evidence_text, source_text) if part)
        return any(
            marker in text
            or marker in combined
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
