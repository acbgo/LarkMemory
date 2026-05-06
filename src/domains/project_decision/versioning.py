from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

from src.storage import MemoryCoreStore

from .models import ProjectDecision


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DecisionVersionDecision:
    should_supersede: bool
    should_reuse_existing: bool = False
    old_memory_id: str | None = None
    new_memory_id: str | None = None
    reason: str = ""
    confidence: float = 0.0
    matched_topic: str | None = None
    detection_source: str = "rule"


class ProjectDecisionVersionManager:
    """Maintains supersede links between project decision memories."""

    def __init__(
        self,
        memory_store: MemoryCoreStore,
        *,
        llm_client: Any | None = None,
        llm_min_confidence: float = 0.75,
    ) -> None:
        self.memory_store = memory_store
        self.llm_client = llm_client
        self.llm_min_confidence = llm_min_confidence

    def detect_update(
        self,
        new_decision: ProjectDecision,
        existing_rows: list[dict[str, object]] | None = None,
        *,
        detection_source: str = "rule",
    ) -> DecisionVersionDecision:
        if new_decision.status != "confirmed":
            return DecisionVersionDecision(
                False,
                reason="new_decision_not_confirmed",
                detection_source=detection_source,
            )
        rows = existing_rows
        if rows is None:
            rows = self.memory_store.list_active_memories(
                domain="project_decision",
                limit=100,
            )
        semantic_mode = existing_rows is not None
        candidates = self._eligible_candidates(
            rows,
            new_decision,
            enforce_topic_threshold=not semantic_mode,
        )
        llm_decision = self._detect_with_llm(
            new_decision,
            candidates,
        )
        if llm_decision is not None:
            return llm_decision
        exact_duplicate = self._detect_exact_duplicate(new_decision, candidates, detection_source=detection_source)
        if exact_duplicate is not None:
            return exact_duplicate
        rule_candidates = self._eligible_candidates(
            rows,
            new_decision,
            enforce_topic_threshold=True,
        )
        best: tuple[float, ProjectDecision] | None = None
        for topic_score, old_decision in rule_candidates:
            if not self._decision_changed(old_decision, new_decision):
                continue
            if best is None or topic_score > best[0]:
                best = (topic_score, old_decision)
        if best is None:
            return DecisionVersionDecision(
                False,
                reason="no_supersede_candidate",
                detection_source=detection_source,
            )
        old = best[1]
        return DecisionVersionDecision(
            True,
            old_memory_id=old.decision_id,
            new_memory_id=new_decision.decision_id,
            reason="same_scope_topic_and_changed_decision",
            confidence=min(0.95, 0.65 + best[0] * 0.3),
            matched_topic=old.topic,
            detection_source=detection_source,
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
                key=lambda decision: (decision.decided_at or "", decision.decision_id),
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
                    key=lambda decision: (decision.decided_at or "", decision.decision_id),
                )
            )
            return ordered
        return sorted(
            decisions,
            key=lambda decision: (decision.decided_at or "", decision.decision_id),
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

    def _eligible_candidates(
        self,
        rows: list[dict[str, object]],
        new_decision: ProjectDecision,
        *,
        enforce_topic_threshold: bool,
    ) -> list[tuple[float, ProjectDecision]]:
        candidates: list[tuple[float, ProjectDecision]] = []
        for row in rows:
            old_decision = ProjectDecision.from_memory_core(row)
            if old_decision.decision_id == new_decision.decision_id:
                continue
            if not self._same_project_scope(old_decision, new_decision):
                continue
            topic_score = self._topic_similarity(old_decision.topic, new_decision.topic)
            if enforce_topic_threshold and topic_score < 0.55:
                continue
            if old_decision.stage and new_decision.stage and old_decision.stage != new_decision.stage:
                continue
            candidates.append((topic_score, old_decision))
        return candidates

    def _detect_exact_duplicate(
        self,
        new_decision: ProjectDecision,
        candidates: list[tuple[float, ProjectDecision]],
        *,
        detection_source: str,
    ) -> DecisionVersionDecision | None:
        best: tuple[float, ProjectDecision] | None = None
        for topic_score, old_decision in candidates:
            if not self._same_decision(old_decision, new_decision):
                continue
            if best is None or topic_score > best[0]:
                best = (topic_score, old_decision)
        if best is None:
            return None
        topic_score, old_decision = best
        same_topic = self._topic_similarity(old_decision.topic, new_decision.topic) >= 0.55
        return DecisionVersionDecision(
            False,
            should_reuse_existing=True,
            old_memory_id=old_decision.decision_id,
            new_memory_id=new_decision.decision_id,
            reason="same_scope_topic_and_same_decision" if same_topic else "same_scope_decision_and_same_decision",
            confidence=min(0.98, 0.7 + max(topic_score, 0.2) * 0.25),
            matched_topic=old_decision.topic,
            detection_source=detection_source,
        )

    def _detect_with_llm(
        self,
        new_decision: ProjectDecision,
        candidates: list[tuple[float, ProjectDecision]],
    ) -> DecisionVersionDecision | None:
        if self.llm_client is None or not candidates:
            return None
        best_duplicate: tuple[float, ProjectDecision, str] | None = None
        best_supersede: tuple[float, ProjectDecision, str] | None = None
        best_new: tuple[float, ProjectDecision, str] | None = None
        for topic_score, old_decision in candidates:
            verdict = self._judge_pair_with_llm(old_decision, new_decision)
            if verdict is None:
                continue
            label = verdict.get("label")
            confidence = self._coerce_confidence(verdict.get("confidence"))
            if label not in {"duplicate", "supersede", "new"}:
                continue
            if confidence < self.llm_min_confidence:
                continue
            reason = str(verdict.get("reason") or "").strip()
            blended = min(0.99, confidence * 0.8 + topic_score * 0.2)
            if label == "duplicate":
                if best_duplicate is None or blended > best_duplicate[0]:
                    best_duplicate = (blended, old_decision, reason)
                continue
            if label == "supersede":
                if best_supersede is None or blended > best_supersede[0]:
                    best_supersede = (blended, old_decision, reason)
                continue
            if best_new is None or blended > best_new[0]:
                best_new = (blended, old_decision, reason)
        if best_duplicate is not None:
            confidence, old_decision, reason = best_duplicate
            return DecisionVersionDecision(
                False,
                should_reuse_existing=True,
                old_memory_id=old_decision.decision_id,
                new_memory_id=new_decision.decision_id,
                reason="llm_duplicate",
                confidence=confidence,
                matched_topic=old_decision.topic,
                detection_source="llm",
            )
        if best_supersede is not None:
            confidence, old_decision, reason = best_supersede
            return DecisionVersionDecision(
                True,
                should_reuse_existing=False,
                old_memory_id=old_decision.decision_id,
                new_memory_id=new_decision.decision_id,
                reason="llm_supersede",
                confidence=confidence,
                matched_topic=old_decision.topic,
                detection_source="llm",
            )
        if best_new is not None:
            confidence, old_decision, reason = best_new
            return DecisionVersionDecision(
                False,
                should_reuse_existing=False,
                old_memory_id=old_decision.decision_id,
                new_memory_id=new_decision.decision_id,
                reason="llm_new",
                confidence=confidence,
                matched_topic=old_decision.topic,
                detection_source="llm",
            )
        return None

    def _judge_pair_with_llm(
        self,
        old_decision: ProjectDecision,
        new_decision: ProjectDecision,
    ) -> dict[str, Any] | None:
        if self.llm_client is None:
            return None
        system_prompt = (
            "你是项目决策记忆的版本关系判断器。"
            "你的任务是判断同一 scope、同一 topic 下，一条新项目决策与一条旧项目决策之间的版本关系。"
            "只允许返回严格 JSON，不得输出 Markdown、解释性文字或多余字段："
            '{"label":"duplicate|supersede|new","confidence":0.0,"reason":"..."}。'
            "\n\n"
            "判断标准："
            "\n"
            "1. duplicate：新结论与旧结论表达的是同一个有效决策，核心方案、状态、对象、约束和原因没有实质变化。"
            "允许措辞变化、补充同义说明、重复确认、轻微信息补全。"
            "\n"
            "2. supersede：新结论使旧结论不再作为当前有效决策，或改变了旧结论的关键字段。"
            "关键字段包括方案选择、是否采用/否决、当前状态、负责人、时间窗口、阈值、范围、优先级、上线/回滚策略、预算结论。"
            "如果新结论包含'改为'、'不再'、'废弃'、'回滚'、'恢复'、'调整为'、'最终以...为准'等语义，通常判断为 supersede。"
            "\n"
            "3. new：新结论与旧结论属于同一 topic，但解决的是另一个独立问题；"
            "它不否定、不替代、不改变旧结论的当前有效性，只是在同 topic 下新增一条可并存的决策。"
            "\n\n"
            "注意："
            "不要因为新旧文本都提到相同实体就判断 duplicate；"
            "不要因为新结论提到旧方案的历史背景就判断 duplicate；"
            "如果新结论明确给出了当前值，并且旧结论中的当前值不同，应判断 supersede；"
            "如果无法确定是否替代，但两条结论可以同时成立，应判断 new。"
        )
        user_prompt = (
            f"topic: {new_decision.topic}\n"
            f"old_conclusion: {self._judgement_text(old_decision)}\n"
            f"new_conclusion: {self._judgement_text(new_decision)}\n"
            "请判断 label。"
        )
        schema = {
            "type": "object",
            "properties": {
                "label": {
                    "type": "string",
                    "enum": ["duplicate", "supersede", "new"],
                },
                "confidence": {"type": "number"},
                "reason": {"type": "string"},
            },
            "required": ["label", "confidence", "reason"],
        }
        try:
            return self._run_async(
                self.llm_client.ajson(
                    system_prompt,
                    user_prompt,
                    schema=schema,
                    temperature=0,
                )
            )
        except Exception:
            logger.warning(
                "action=llm_version_judge_failed topic=%s old_memory_id=%s new_memory_id=%s",
                new_decision.topic,
                old_decision.decision_id,
                new_decision.decision_id,
                exc_info=True,
            )
            return None

    @staticmethod
    def _run_async(awaitable: Any) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(awaitable)
        raise RuntimeError("ProjectDecisionVersionManager cannot block inside an async context.")

    @staticmethod
    def _judgement_text(decision: ProjectDecision) -> str:
        return (decision.conclusion or decision.decision).strip()

    @staticmethod
    def _coerce_confidence(value: object) -> float:
        if not isinstance(value, (int, float)):
            return 0.0
        return max(0.0, min(1.0, float(value)))

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
        old_text = self._canonical_decision_text(old)
        new_text = self._canonical_decision_text(new)
        if old_text == new_text:
            return False
        change_signals = ("改为", "调整为", "延期", "提前", "替换", "不再", "改成", "从", "变更")
        if any(signal in new_text for signal in change_signals):
            return True
        old_alternatives = set(old.alternatives)
        new_alternatives = set(new.alternatives)
        if old_alternatives and new_alternatives and old_alternatives != new_alternatives:
            return True
        if old.decision and new.decision and old.decision != new.decision:
            return True
        return False

    def _same_decision(self, old: ProjectDecision, new: ProjectDecision) -> bool:
        old_text = self._canonical_decision_text(old)
        new_text = self._canonical_decision_text(new)
        return bool(old_text and new_text and old_text == new_text)

    def _canonical_decision_text(self, decision: ProjectDecision) -> str:
        text = (decision.conclusion or decision.decision).strip()
        if not text:
            return ""
        text = re.sub(r"^(我们|再次|重新|已|最终|现已|现阶段|目前)+", "", text)
        text = re.sub(r"^(决定|确认|拍板|采用|选择|结论是)\s*", "", text)
        text = re.split(r"(因为|考虑到|由于|原因是)", text, maxsplit=1)[0]
        return text.strip()
