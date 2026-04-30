from __future__ import annotations

import logging
import asyncio
import re
from typing import Any

from src.schemas import EventContext, NormalizedEvent
from src.utils.text import clean_text

from .models import (
    ProjectDecision,
    ProjectDecisionCandidate,
)


DECISION_KEYWORDS = (
    "决定",
    "确认",
    "拍板",
    "采用",
    "选择",
    "结论",
    "最终",
    "不采用",
    "否决",
    "截止日期",
    "deadline",
    "decision",
    "decided",
    "choose",
    "confirmed",
)

REASON_KEYWORDS = (
    "因为",
    "原因",
    "考虑到",
    "理由",
    "风险",
    "约束",
    "避免",
    "由于",
    "why",
    "rationale",
)

ALTERNATIVE_PATTERNS = (
    r"方案\s*[A-Za-z0-9一二三四五六七八九十]+",
    r"[A-Za-z0-9一二三四五六七八九十]+/[A-Za-z0-9一二三四五六七八九十]+",
    r"用.+而不是.+",
    r"选择.+不选.+",
)
ALTERNATIVE_PATTERN = re.compile(r"方案\s*([A-Za-z0-9一二三四五六七八九十]+)")
DEADLINE_PATTERN = re.compile(r"(截止日期|deadline)[是为:：\s]*([^，。；;\n]+)")
SENTENCE_SPLIT_PATTERN = re.compile(r"[。！？\n;；]+")
logger = logging.getLogger(__name__)


_LLM_EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "memories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "content": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["topic", "content", "confidence"],
            },
        },
    },
    "required": ["memories"],
}

_LLM_EXTRACTION_SYSTEM_PROMPT = """Return JSON only: {"memories":[{"topic":"...","content":"...","confidence":0.8}]}.
Extract project decision memories only. If there is no project decision, return {"memories":[]}.
Keep topic short. Put the decision or conclusion in content."""


class ProjectDecisionExtractor:
    """Rule-based project decision extractor with an optional LLM hook."""

    def __init__(self, llm_client: Any | None = None, *, min_confidence: float = 0.45) -> None:
        self.llm_client = llm_client
        self.min_confidence = min_confidence

    def extract(self, event: NormalizedEvent) -> list[ProjectDecisionCandidate]:
        text = self.collect_text(event)
        if self.llm_client is None and not self.has_decision_signal(text):
            logger.info(
                "action=no_signal event_id=%s text_length=%s",
                event.event_id,
                len(text),
            )
            return []
        candidates = self.extract_from_text(text, context=event.context, event=event)
        admitted = [
            candidate
            for candidate in candidates
            if candidate.is_admissible(self.min_confidence)
        ]
        admitted_confidence = [
            candidate.decision.confidence
            for candidate in admitted
        ]
        logger.info(
            "action=done event_id=%s raw_candidate_count=%s admitted_count=%s admitted_confidence=%s min_confidence=%.2f",
            event.event_id,
            len(candidates),
            len(admitted),
            admitted_confidence,
            self.min_confidence,
        )
        return admitted

    def extract_from_text(
        self,
        text: str,
        *,
        context: EventContext | None = None,
        event: NormalizedEvent | None = None,
    ) -> list[ProjectDecisionCandidate]:
        if self.llm_client is not None:
            try:
                candidates = self._extract_with_llm(text, context=context, event=event)
            except Exception:
                logger.exception(
                    "action=llm_failed fallback=rule_based"
                )
            else:
                logger.info(
                    "action=llm_candidates_done candidate_count=%s",
                    len(candidates),
                )
                return candidates

        candidates = self._extract_rule_based(text, context=context, event=event)
        logger.info(
            "action=extract_rule_based cond candidate_count=%s llm_enabled=%s",
            len(candidates),
            self.llm_client is not None,
        )
        return candidates

    def collect_text(self, event: NormalizedEvent) -> str:
        """Collect searchable decision text from event title, content, payload, and raw payload."""

        parts: list[str] = []
        for value in (event.title, event.content_text):
            cleaned = clean_text(value)
            if cleaned:
                parts.append(cleaned)
        for key in ("text", "content", "message", "summary", "body"):
            value = event.payload.get(key)
            if isinstance(value, str) and clean_text(value):
                parts.append(clean_text(value))
        parts.extend(self._string_values(event.payload))
        parts.extend(self._string_values(event.raw_payload))
        return clean_text(" ".join(dict.fromkeys(part for part in parts if part)))

    def has_decision_signal(self, text: str | None) -> bool:
        """未启用LLM的时候，fallback到规则匹配"""
        text = clean_text(text)
        if not text:
            return False
        lowered = text.lower()
        if any(keyword in text for keyword in ("决定", "拍板", "采用", "选择", "结论", "最终", "不采用", "否决")):
            return True
        if any(keyword in lowered for keyword in ("deadline", "decision", "decided", "choose", "confirmed")):
            return True
        if "方案" in text and any(keyword in text for keyword in ("采用", "不采用", "选择", "不选", "改为")):
            return True
        if any(keyword in text for keyword in ("截止日期", "上线时间", "负责人")) and "确认" in text:
            return True
        return False

    def _extract_rule_based(
        self,
        text: str,
        *,
        context: EventContext | None,
        event: NormalizedEvent | None,
    ) -> list[ProjectDecisionCandidate]:
        cleaned = clean_text(text)
        if not cleaned:
            return []
        sentences = self._split_sentences(cleaned)
        decision_index = self._find_decision_sentence_index(sentences)
        evidence_text = sentences[decision_index] if decision_index >= 0 else cleaned
        status = self._infer_status(cleaned)
        topic = self._infer_topic(cleaned, event=event)
        decision_text = self._infer_decision_text(evidence_text)
        confidence = self._infer_confidence(cleaned, status)
        alternatives = self._extract_alternatives(cleaned)
        reasons = self._extract_reasons(sentences, decision_index, event=event)
        if "截止日期" in cleaned or "deadline" in cleaned.lower():
            topic = "截止日期"
        signals = [keyword for keyword in DECISION_KEYWORDS if keyword.lower() in cleaned.lower()]
        return [
            self._build_candidate(
                topic=topic,
                decision_text=decision_text,
                evidence_text=evidence_text,
                context=context,
                event=event,
                reasons=reasons,
                alternatives=alternatives,
                confidence=confidence,
                signals=signals,
                status=status,
            )
        ]

    def _build_candidate(
        self,
        *,
        topic: str,
        decision_text: str,
        evidence_text: str,
        context: EventContext | None,
        event: NormalizedEvent | None,
        reasons: list[str] | None = None,
        objections: list[str] | None = None,
        alternatives: list[str] | None = None,
        confidence: float = 0.5,
        signals: list[str] | None = None,
        status: str = "confirmed",
    ) -> ProjectDecisionCandidate:
        important_terms = ("截止", "架构", "选型", "负责人", "上线")
        decision = ProjectDecision(
            project_id=context.project_id if context else None,
            workspace_id=context.workspace_id if context else None,
            team_id=context.team_id if context else None,
            thread_id=context.thread_id if context else None,
            topic=topic,
            decision=decision_text,
            conclusion=decision_text,
            stage=self._stage_from_payload(event.payload if event else {}),
            status=status,  # type: ignore[arg-type]
            alternatives=alternatives or [],
            reasons=reasons or [],
            objections=objections or [],
            source_event_id=event.event_id if event else None,
            source_type=event.source_type if event else "feishu_chat",
            source_ref=self._source_ref(context, event),
            decided_at=event.occurred_at if event else None,
            confidence=confidence,
            importance=0.85 if any(term in evidence_text for term in important_terms) else 0.7,
        )
        return ProjectDecisionCandidate(
            decision=decision,
            evidence_text=evidence_text,
            signals=signals or [],
            needs_review=confidence < 0.65,
        )

    def _extract_with_llm(
        self,
        text: str,
        *,
        context: EventContext | None,
        event: NormalizedEvent | None,
    ) -> list[ProjectDecisionCandidate]:
        raw = _run_async(
            self.llm_client.ajson(  # type: ignore[union-attr]
                _LLM_EXTRACTION_SYSTEM_PROMPT,
                self._build_llm_user_prompt(text, context=context, event=event),
                schema=_LLM_EXTRACTION_SCHEMA,
                max_tokens=1024,
            )
        )
        memories = raw.get("memories") if isinstance(raw.get("memories"), list) else []
        logger.info(
            "action=extract_with_llm parsed event_id=%s raw_memory_count=%s",
            event.event_id if event else None,
            len(memories),
        )

        candidates: list[ProjectDecisionCandidate] = []
        for item in memories:
            if not isinstance(item, dict):
                continue
            candidate = self._candidate_from_llm_item(item, context=context, event=event)
            if candidate is not None:
                candidates.append(candidate)
        logger.info(
            "action=extract_with_llm done event_id=%s candidate_count=%s",
            event.event_id if event else None,
            len(candidates),
        )
        return candidates

    def _build_llm_user_prompt(
        self,
        text: str,
        *,
        context: EventContext | None,
        event: NormalizedEvent | None,
    ) -> str:
        """Build a compact extraction prompt with source context for the LLM."""
        return (
            "Extract project decision memories from this event.\n"
            f"event_id={event.event_id if event else None}\n"
            f"occurred_at={event.occurred_at if event else None}\n"
            f"source_type={event.source_type if event else None}\n"
            f"context={context}\n"
            f"text={text}"
        )

    def _candidate_from_llm_item(
        self,
        item: dict[str, Any],
        *,
        context: EventContext | None,
        event: NormalizedEvent | None,
    ) -> ProjectDecisionCandidate | None:
        """Convert one LLM decision object into a validated project decision candidate."""
        topic = clean_text(str(item.get("topic") or ""), max_chars=120)
        decision_text = clean_text(str(item.get("content") or ""), max_chars=240)
        evidence_text = decision_text
        if not topic or not decision_text:
            return None
        confidence = _as_float(item.get("confidence"), default=0.7)
        decision = ProjectDecision(
            project_id=context.project_id if context else None,
            workspace_id=context.workspace_id if context else None,
            team_id=context.team_id if context else None,
            thread_id=context.thread_id if context else None,
            topic=topic,
            decision=decision_text,
            conclusion=decision_text,
            status="confirmed",
            source_event_id=event.event_id if event else None,
            source_type=event.source_type if event else "feishu_chat",
            source_ref=self._source_ref(context, event),
            decided_at=event.occurred_at if event else None,
            confidence=max(0.0, min(1.0, confidence)),
            importance=0.7,
        )
        return ProjectDecisionCandidate(
            decision=decision,
            evidence_text=evidence_text,
            signals=["llm_extraction"],
            needs_review=confidence < 0.65,
        )

    def _string_values(self, value: Any) -> list[str]:
        if isinstance(value, str):
            cleaned = clean_text(value)
            return [cleaned] if cleaned else []
        if isinstance(value, dict):
            result: list[str] = []
            for nested in value.values():
                result.extend(self._string_values(nested))
            return result
        if isinstance(value, list):
            result = []
            for nested in value:
                result.extend(self._string_values(nested))
            return result
        return []

    def _infer_status(self, text: str) -> str:
        if any(keyword in text for keyword in ("决定", "确认", "拍板", "采用", "选择", "结论", "最终")):
            return "confirmed"
        if any(keyword in text.lower() for keyword in ("decided", "confirmed", "choose")):
            return "confirmed"
        return "confirmed"

    def _infer_topic(self, text: str, *, event: NormalizedEvent | None) -> str:
        if event and event.title:
            return clean_text(event.title, max_chars=80)
        if "截止日期" in text or "deadline" in text.lower():
            return "截止日期"
        if "方案" in text:
            return "方案选择"
        if "数据库" in text:
            return "数据库选型"
        return clean_text(text, max_chars=60)

    def _infer_decision_text(self, text: str) -> str:
        deadline_match = DEADLINE_PATTERN.search(text)
        if deadline_match:
            return f"确认截止日期是 {clean_text(deadline_match.group(2), max_chars=40)}"
        for marker in ("决定", "确认", "拍板", "采用", "选择", "结论"):
            if marker in text:
                return clean_text(text[text.index(marker):], max_chars=160)
        return clean_text(text, max_chars=160)

    def _infer_confidence(self, text: str, status: str) -> float:
        score = 0.45
        if status == "confirmed":
            score += 0.25
        if any(keyword in text for keyword in REASON_KEYWORDS):
            score += 0.1
        if ALTERNATIVE_PATTERN.search(text):
            score += 0.1
        if DEADLINE_PATTERN.search(text):
            score += 0.1
        return min(score, 0.95)

    def _extract_alternatives(self, text: str) -> list[str]:
        names = [f"方案 {match.group(1)}" for match in ALTERNATIVE_PATTERN.finditer(text)]
        return list(dict.fromkeys(names))

    def _extract_reasons(
        self,
        sentences: list[str],
        decision_index: int,
        *,
        event: NormalizedEvent | None,
    ) -> list[str]:
        reasons: list[str] = []
        if not sentences:
            return reasons
        start = max(decision_index - 2, 0)
        end = min(decision_index + 3, len(sentences))
        nearby = sentences[start:end]
        text = "。".join(nearby)
        for marker in ("因为", "原因是", "考虑到", "由于"):
            if marker in text:
                reason_text = clean_text(text.split(marker, 1)[1], max_chars=120)
                if reason_text:
                    reasons.append(reason_text)
                break
        return reasons

    def _split_sentences(self, text: str) -> list[str]:
        return [clean_text(sentence) for sentence in SENTENCE_SPLIT_PATTERN.split(text) if clean_text(sentence)]

    def _find_decision_sentence_index(self, sentences: list[str]) -> int:
        for index, sentence in enumerate(sentences):
            if self.has_decision_signal(sentence):
                return index
        return 0

    def _stage_from_payload(self, payload: dict[str, Any]) -> str | None:
        for key in ("stage", "project_stage", "phase"):
            value = payload.get(key)
            if isinstance(value, str) and clean_text(value):
                return clean_text(value)
        return None

    def _source_ref(
        self,
        context: EventContext | None,
        event: NormalizedEvent | None,
    ) -> str | None:
        if event:
            for key in ("source_ref", "message_id", "doc_id", "meeting_id"):
                value = event.payload.get(key)
                if isinstance(value, str) and clean_text(value):
                    return clean_text(value)
        if context and context.thread_id:
            return context.thread_id
        return event.event_id if event else None


def _run_async(awaitable: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    raise RuntimeError("ProjectDecisionExtractor sync API cannot run inside an active event loop")


def _as_float(value: object, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
