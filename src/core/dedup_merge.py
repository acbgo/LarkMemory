from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any

from src.schemas import MemoryCore
from src.utils.text import clean_text
from src.utils.time import utc_now_iso


@dataclass(slots=True)
class DedupResult:
    duplicate_found: bool
    matched_memory_id: str | None = None
    score: float = 0.0
    reason: str = ""
    merged_memory: MemoryCore | None = None


def memory_from_row(row: MemoryCore | dict[str, Any]) -> MemoryCore:
    if isinstance(row, MemoryCore):
        return row
    data = dict(row)
    data["entities"] = data.get("entities") or data.get("entities_json") or []
    data["tags"] = data.get("tags") or data.get("tags_json") or []
    allowed = MemoryCore.__dataclass_fields__.keys()
    return MemoryCore(**{key: data.get(key) for key in allowed})  # type: ignore[arg-type]


class DedupMergeEngine:
    def __init__(self, duplicate_threshold: float = 0.9, merge_threshold: float = 0.75) -> None:
        self.duplicate_threshold = duplicate_threshold
        self.merge_threshold = merge_threshold

    def similarity(self, left: str, right: str) -> float:
        left_clean = clean_text(left).lower()
        right_clean = clean_text(right).lower()
        if not left_clean or not right_clean:
            return 0.0
        if left_clean == right_clean:
            return 1.0
        left_tokens = self._tokens(left_clean)
        right_tokens = self._tokens(right_clean)
        if not left_tokens or not right_tokens:
            left_tokens = self._bigrams(left_clean)
            right_tokens = self._bigrams(right_clean)
        if not left_tokens or not right_tokens:
            return 0.0
        return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)

    def find_duplicate(
        self,
        candidate: MemoryCore,
        existing: list[MemoryCore | dict[str, Any]],
    ) -> DedupResult:
        best_memory: MemoryCore | None = None
        best_score = 0.0
        for item in existing:
            memory = memory_from_row(item)
            if memory.domain != candidate.domain or memory.scope != candidate.scope:
                continue
            if memory.status in {"expired", "forgotten"}:
                continue
            score = self.similarity(candidate.content_text, memory.content_text)
            if score > best_score:
                best_score = score
                best_memory = memory

        if best_memory is None:
            return DedupResult(False, reason="no comparable memory")
        if best_score >= self.duplicate_threshold:
            return DedupResult(
                True,
                matched_memory_id=best_memory.memory_id,
                score=best_score,
                reason="duplicate threshold matched",
            )
        if best_score >= self.merge_threshold:
            return DedupResult(
                False,
                matched_memory_id=best_memory.memory_id,
                score=best_score,
                reason="merge threshold matched",
                merged_memory=self.merge(candidate, best_memory),
            )
        return DedupResult(False, score=best_score, reason="no duplicate")

    def merge(self, candidate: MemoryCore, existing: MemoryCore | dict[str, Any]) -> MemoryCore:
        current = memory_from_row(existing)
        content = (
            candidate.content_text
            if len(candidate.content_text) > len(current.content_text)
            else current.content_text
        )
        return replace(
            current,
            content_text=content,
            tags=self._merge_list(current.tags, candidate.tags),
            entities=self._merge_list(current.entities, candidate.entities),
            importance=max(current.importance, candidate.importance),
            confidence=max(current.confidence, candidate.confidence),
            status="active" if "active" in {current.status, candidate.status} else current.status,
            updated_at=utc_now_iso(),
        )

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return set(re.findall(r"[a-zA-Z0-9_]+", text))

    @staticmethod
    def _bigrams(text: str) -> set[str]:
        compact = re.sub(r"\s+", "", text)
        return {compact[index : index + 2] for index in range(max(len(compact) - 1, 0))}

    @staticmethod
    def _merge_list(left: list[str], right: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in [*left, *right]:
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(value)
        return result
