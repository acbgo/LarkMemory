from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.schemas import MemoryCore, NormalizedEvent
from src.utils.text import clean_text, contains_any


@dataclass(slots=True)
class AdmissionDecision:
    admitted: bool
    status: str = "candidate"
    importance: float = 0.5
    confidence: float = 0.5
    reason: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class AdmissionController:
    def __init__(
        self,
        min_content_length: int = 8,
        direct_admit_importance: float = 0.75,
        candidate_confidence_threshold: float = 0.35,
    ) -> None:
        self.min_content_length = min_content_length
        self.direct_admit_importance = direct_admit_importance
        self.candidate_confidence_threshold = candidate_confidence_threshold

    def evaluate_event(
        self,
        event: NormalizedEvent,
        *,
        domain: str | None = None,
    ) -> AdmissionDecision:
        text = clean_text(event.content_text or event.title)
        has_payload = bool(event.payload or event.raw_payload)
        if event.event_type == "memory_feedback":
            return AdmissionDecision(True, status="active", importance=0.8, confidence=0.8, reason="feedback event")
        if not text and not has_payload:
            return AdmissionDecision(False, reason="empty event")
        if event.event_type in {"command_finished", "command_failed"} and has_payload:
            return AdmissionDecision(True, status="candidate", importance=0.55, confidence=0.55, reason="command event")
        strong_signal = contains_any(
            text,
            ["决定", "必须", "截止", "风险", "偏好", "默认", "部署命令", "decision", "must", "deadline", "risk", "prefer"],
        )
        if strong_signal:
            return AdmissionDecision(
                True,
                status="active",
                importance=0.8,
                confidence=0.75,
                reason="strong memory signal",
                metadata={"domain": domain},
            )
        if len(text) < self.min_content_length and not has_payload:
            return AdmissionDecision(False, reason="content too short")
        return AdmissionDecision(True, status="candidate", importance=0.45, confidence=0.45, reason="candidate event")

    def evaluate_memory(self, memory: MemoryCore) -> AdmissionDecision:
        if not clean_text(memory.content_text):
            return AdmissionDecision(False, reason="empty memory")
        if (
            memory.importance >= self.direct_admit_importance
            and memory.confidence >= self.candidate_confidence_threshold
        ):
            return AdmissionDecision(
                True,
                status="active",
                importance=memory.importance,
                confidence=memory.confidence,
                reason="high importance memory",
            )
        if memory.confidence < self.candidate_confidence_threshold:
            return AdmissionDecision(
                True,
                status="candidate",
                importance=memory.importance,
                confidence=memory.confidence,
                reason="low confidence candidate",
            )
        return AdmissionDecision(
            True,
            status=memory.status,
            importance=memory.importance,
            confidence=memory.confidence,
            reason="memory admitted",
        )

    @staticmethod
    def should_promote(decision: AdmissionDecision) -> bool:
        return decision.admitted and decision.status == "active"
