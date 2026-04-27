from __future__ import annotations

import re
from dataclasses import dataclass

from src.storage import MemoryCoreStore, TeamRetentionMemory, TeamRetentionStore


@dataclass(slots=True)
class TeamRetentionVersionDecision:
    should_supersede: bool
    old_memory_id: str | None = None
    new_memory_id: str | None = None
    reason: str = ""
    confidence: float = 0.0


class TeamRetentionVersionManager:
    def __init__(
        self,
        memory_store: MemoryCoreStore,
        team_retention_store: TeamRetentionStore,
    ) -> None:
        self.memory_store = memory_store
        self.team_retention_store = team_retention_store

    def detect_update(
        self,
        new_memory: TeamRetentionMemory,
        existing_rows: list[dict[str, object]] | None = None,
    ) -> TeamRetentionVersionDecision:
        rows = existing_rows
        if rows is None:
            rows = self.memory_store.list_active_memories(
                domain="team_retention",
                limit=100,
            )
        best: tuple[float, TeamRetentionMemory] | None = None
        for row in rows:
            old_memory = self.team_retention_store.get_memory(str(row["memory_id"]))
            if old_memory is None:
                old_memory = TeamRetentionMemory.from_memory_core(row)  # type: ignore[arg-type]
            if old_memory.retention_id == new_memory.retention_id:
                continue
            if not self._same_scope(old_memory, new_memory):
                continue
            if old_memory.fact_type != new_memory.fact_type:
                continue
            version_score = self._version_group_score(old_memory, new_memory)
            fact_score = self._fact_similarity(old_memory.fact_value, new_memory.fact_value)
            if version_score < 0.6 and fact_score < 0.35:
                continue
            if old_memory.fact_value.strip() == new_memory.fact_value.strip():
                continue
            score = max(version_score, fact_score)
            if best is None or score > best[0]:
                best = (score, old_memory)
        if best is None:
            return TeamRetentionVersionDecision(False, reason="no_supersede_candidate")
        return TeamRetentionVersionDecision(
            True,
            old_memory_id=best[1].retention_id,
            new_memory_id=new_memory.retention_id,
            reason="same_scope_fact_type_and_changed_value",
            confidence=min(0.95, 0.65 + best[0] * 0.3),
        )

    def apply_supersede(self, old_memory_id: str, new_memory_id: str) -> None:
        self.memory_store.mark_superseded(old_memory_id, new_memory_id)
        self.team_retention_store.update_memory_links(old_memory_id, superseded_by=new_memory_id)
        self.team_retention_store.update_memory_links(new_memory_id, overwrite_of=old_memory_id)
        self.team_retention_store.deactivate_review(old_memory_id)

    def _same_scope(self, left: TeamRetentionMemory, right: TeamRetentionMemory) -> bool:
        if left.team_id and right.team_id:
            return left.team_id == right.team_id
        if left.project_id and right.project_id:
            return left.project_id == right.project_id
        if left.workspace_id and right.workspace_id:
            return left.workspace_id == right.workspace_id
        return False

    def _version_group_score(self, left: TeamRetentionMemory, right: TeamRetentionMemory) -> float:
        if left.version_group and right.version_group and left.version_group == right.version_group:
            return 1.0
        return 0.0

    def _fact_similarity(self, left: str, right: str) -> float:
        left_tokens = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]+", left.lower()))
        right_tokens = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]+", right.lower()))
        if not left_tokens or not right_tokens:
            return 0.0
        return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
