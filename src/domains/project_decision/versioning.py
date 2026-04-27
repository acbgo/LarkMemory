from __future__ import annotations

import re
from dataclasses import dataclass

from src.storage import MemoryCoreStore

from .models import ProjectDecision


@dataclass(slots=True)
class DecisionVersionDecision:
    should_supersede: bool
    old_memory_id: str | None = None
    new_memory_id: str | None = None
    reason: str = ""
    confidence: float = 0.0
    matched_topic: str | None = None


class ProjectDecisionVersionManager:
    """Maintains supersede links between project decision memories."""

    def __init__(self, memory_store: MemoryCoreStore) -> None:
        self.memory_store = memory_store

    def detect_update(
        self,
        new_decision: ProjectDecision,
        existing_rows: list[dict[str, object]] | None = None,
    ) -> DecisionVersionDecision:
        if new_decision.status != "confirmed":
            return DecisionVersionDecision(False, reason="new_decision_not_confirmed")
        rows = existing_rows
        if rows is None:
            rows = self.memory_store.list_active_memories(
                domain="project_decision",
                limit=100,
            )
        best: tuple[float, ProjectDecision] | None = None
        for row in rows:
            old_decision = ProjectDecision.from_memory_core(row)
            if old_decision.decision_id == new_decision.decision_id:
                continue
            if not self._same_project_scope(old_decision, new_decision):
                continue
            topic_score = self._topic_similarity(old_decision.topic, new_decision.topic)
            if topic_score < 0.55:
                continue
            if old_decision.stage and new_decision.stage and old_decision.stage != new_decision.stage:
                continue
            if not self._decision_changed(old_decision, new_decision):
                continue
            if best is None or topic_score > best[0]:
                best = (topic_score, old_decision)
        if best is None:
            return DecisionVersionDecision(False, reason="no_supersede_candidate")
        old = best[1]
        return DecisionVersionDecision(
            True,
            old_memory_id=old.decision_id,
            new_memory_id=new_decision.decision_id,
            reason="same_scope_topic_and_changed_decision",
            confidence=min(0.95, 0.65 + best[0] * 0.3),
            matched_topic=old.topic,
        )

    def apply_supersede(self, old_memory_id: str, new_memory_id: str) -> None:
        if not old_memory_id or not new_memory_id:
            raise ValueError("old_memory_id and new_memory_id are required")
        self.memory_store.mark_superseded(old_memory_id, new_memory_id)

    def get_version_chain(self, memory_id: str) -> list[ProjectDecision]:
        """Returns version chain rows sorted from older decisions to newer ones."""
        rows = self.memory_store.get_version_chain(memory_id)
        decisions = [ProjectDecision.from_memory_core(row) for row in rows]
        by_id = {decision.decision_id: decision for decision in decisions}
        roots = [
            decision
            for decision in decisions
            if not decision.overwrite_of or decision.overwrite_of not in by_id
        ]
        if roots:
            ordered: list[ProjectDecision] = []
            current = sorted(
                roots,
                key=lambda decision: (decision.decided_at or decision.valid_from or "", decision.decision_id),
            )[0]
            seen: set[str] = set()
            while current.decision_id not in seen:
                ordered.append(current)
                seen.add(current.decision_id)
                next_id = current.superseded_by
                if not next_id or next_id not in by_id:
                    break
                current = by_id[next_id]
            ordered.extend(
                sorted(
                    [decision for decision in decisions if decision.decision_id not in seen],
                    key=lambda decision: (decision.decided_at or decision.valid_from or "", decision.decision_id),
                )
            )
            return ordered
        return sorted(
            decisions,
            key=lambda decision: (decision.decided_at or decision.valid_from or "", decision.decision_id),
        )

    def find_related_decisions(
        self,
        decision: ProjectDecision,
        *,
        limit: int = 20,
    ) -> list[ProjectDecision]:
        rows = self.memory_store.list_active_memories(
            domain="project_decision",
            limit=max(limit * 3, 50),
        )
        related: list[ProjectDecision] = []
        for row in rows:
            candidate = ProjectDecision.from_memory_core(row)
            if candidate.decision_id == decision.decision_id:
                continue
            if not self._same_project_scope(candidate, decision):
                continue
            if self._topic_similarity(candidate.topic, decision.topic) >= 0.5 or (
                candidate.stage and candidate.stage == decision.stage
            ):
                related.append(candidate)
        return related[:limit]

    def _same_project_scope(self, left: ProjectDecision, right: ProjectDecision) -> bool:
        if left.project_id and right.project_id:
            return left.project_id == right.project_id
        if left.team_id and right.team_id:
            return left.team_id == right.team_id
        if left.workspace_id and right.workspace_id:
            return (
                left.workspace_id == right.workspace_id
                and self._topic_similarity(left.topic, right.topic) >= 0.7
            )
        return False

    def _topic_similarity(self, left: str, right: str) -> float:
        left_clean = left.strip().lower()
        right_clean = right.strip().lower()
        if not left_clean or not right_clean:
            return 0.0
        if left_clean == right_clean:
            return 1.0
        if left_clean in right_clean or right_clean in left_clean:
            return 0.8
        left_tokens = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]+", left_clean))
        right_tokens = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]+", right_clean))
        if not left_tokens or not right_tokens:
            return 0.0
        return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)

    def _decision_changed(self, old: ProjectDecision, new: ProjectDecision) -> bool:
        old_text = (old.conclusion or old.decision).strip()
        new_text = (new.conclusion or new.decision).strip()
        if old_text == new_text:
            return False
        change_signals = ("改为", "调整为", "延期", "提前", "替换", "不再", "改成", "从", "变更")
        if any(signal in new_text for signal in change_signals):
            return True
        old_confirmed = {alternative.name for alternative in old.alternatives if alternative.status == "confirmed"}
        new_confirmed = {alternative.name for alternative in new.alternatives if alternative.status == "confirmed"}
        if old_confirmed and new_confirmed and old_confirmed != new_confirmed:
            return True
        if old.decision and new.decision and old.decision != new.decision:
            return True
        return False
