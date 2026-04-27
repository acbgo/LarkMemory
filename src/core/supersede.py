from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.core.dedup_merge import memory_from_row
from src.schemas import MemoryCore
from src.storage import MemoryCoreStore
from src.utils.text import contains_any


@dataclass(slots=True)
class SupersedeDecision:
    should_supersede: bool
    old_memory_id: str | None = None
    new_memory_id: str | None = None
    reason: str = ""
    confidence: float = 0.0


class SupersedeManager:
    def __init__(self, memory_store: MemoryCoreStore) -> None:
        self.memory_store = memory_store

    def detect_conflict(
        self,
        candidate: MemoryCore,
        existing: list[MemoryCore | dict[str, Any]],
    ) -> SupersedeDecision:
        for item in existing:
            memory = memory_from_row(item)
            if (
                memory.domain != candidate.domain
                or memory.scope != candidate.scope
                or memory.memory_type != candidate.memory_type
            ):
                continue
            overlap = set(t.lower() for t in memory.tags + memory.entities) & set(
                t.lower() for t in candidate.tags + candidate.entities
            )
            if not overlap:
                continue
            if contains_any(candidate.content_text, ["改为", "不再", "替换", "改成", "更新为", "change to", "replace"]):
                confidence = 0.75
                if self._is_later(candidate, memory):
                    confidence = 0.9
                return SupersedeDecision(
                    True,
                    old_memory_id=memory.memory_id,
                    new_memory_id=candidate.memory_id,
                    reason="replacement language with overlapping topic",
                    confidence=confidence,
                )
        return SupersedeDecision(False, reason="no conservative conflict matched")

    def mark_superseded(self, old_memory_id: str, new_memory_id: str) -> None:
        self.memory_store.mark_superseded(old_memory_id, new_memory_id)

    def get_version_chain(self, memory_id: str) -> list[dict[str, Any]]:
        return self.memory_store.get_version_chain(memory_id)

    @staticmethod
    def _is_later(candidate: MemoryCore, existing: MemoryCore) -> bool:
        candidate_time = candidate.valid_from or candidate.created_at or ""
        existing_time = existing.valid_from or existing.created_at or ""
        return bool(candidate_time and candidate_time > existing_time)
