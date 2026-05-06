from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from src.schemas import MemoryCore, NormalizedEvent
from src.utils.text import clean_text, contains_any


logger = logging.getLogger(__name__)


_MEMORY_WORTHINESS_SYSTEM_PROMPT = """Return JSON only: {"should_extract": true} or {"should_extract": false}.
Classify whether this workplace event contains durable information worth long-term memory.
True examples: decisions, requirements, deadlines, risks, preferences, reusable workflow knowledge.
False examples: greetings, acknowledgements, casual chatter, one-off coordination."""


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
        llm_client: Any | None = None,
    ) -> None:
        self.min_content_length = min_content_length
        self.direct_admit_importance = direct_admit_importance
        self.candidate_confidence_threshold = candidate_confidence_threshold
        self.llm_client = llm_client

    def evaluate_event(
        self,
        event: NormalizedEvent,
        *,
        domain: str | None = None,
    ) -> AdmissionDecision:
        text = clean_text(event.content_text or event.title)
        if _is_openclaw_retrieval_question(event, text):
            return AdmissionDecision(
                False,
                reason="openclaw retrieval question; skip memory extraction",
                metadata={"domain": domain},
            )

        if self.llm_client is not None:
            llm_decision = self._evaluate_event_with_llm(event, domain=domain)
            if llm_decision is not None:
                return llm_decision

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

    def _evaluate_event_with_llm(
        self,
        event: NormalizedEvent,
        *,
        domain: str | None,
    ) -> AdmissionDecision | None:
        """Use the LLM as the event admission gate; failures fall back to rule admission."""

        try:
            raw = _run_async(
                self.llm_client.ajson(  # type: ignore[union-attr]
                    _MEMORY_WORTHINESS_SYSTEM_PROMPT,
                    f"Judge whether this event should be extracted into long-term memory:\n{event.content_text}",
                    max_tokens=1024,
                )
            )
        except Exception:
            logger.exception(
                "action=llm_memory_gate_failed event_id=%s fallback=rules",
                event.event_id,
            )
            return None

        should_extract = bool(raw.get("should_extract"))
        logger.info(
            "action=llm_memory_gate event_id=%s should_extract=%s",
            event.event_id,
            should_extract,
        )
        if not should_extract:
            return AdmissionDecision(
                False,
                reason="LLM judged no long-term memory extraction needed",
                metadata={"domain": domain, "llm": raw},
            )
        return AdmissionDecision(
            True,
            status="candidate",
            importance=0.5,
            confidence=0.6,
            reason="LLM admitted event",
            metadata={"domain": domain, "llm": raw},
        )

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


def _run_async(awaitable: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    else:
        raise RuntimeError("AdmissionController sync API cannot run inside an active event loop")


def _is_openclaw_retrieval_question(event: NormalizedEvent, text: str) -> bool:
    """Detect OpenClaw query messages that should only trigger retrieval."""
    if event.source_type != "openclaw" or not text:
        return False
    teaching_markers = ("记住", "以后", "下次", "默认", "设置为", "设为", "用命令", "命令是", "按这个命令")
    if any(marker in text for marker in teaching_markers):
        return False
    question_markers = ("?", "？", "什么", "怎么", "如何", "多少", "哪", "是否", "有没有", "最经常", "常用")
    return any(marker in text for marker in question_markers)
