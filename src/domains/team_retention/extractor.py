from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from src.schemas import EventContext, NormalizedEvent
from src.storage import TeamRetentionMemory
from src.utils.text import clean_text


SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_\s-]*key|secret|token|password|passwd|pwd)(\s*[:=]\s*)([A-Za-z0-9_\-./+=]{6,})"),
    re.compile(r"\b(sk-[A-Za-z0-9_\-]{8,})\b"),
    re.compile(r"\b(AKIA[0-9A-Z]{12,})\b"),
)


RETENTION_KEYWORDS = (
    "长期记住",
    "团队记住",
    "不要忘",
    "请记录",
    "需要保留",
    "复习提醒",
    "客户要求",
    "客户偏好",
    "API key",
    "api key",
    "密钥",
    "合规",
    "风险",
    "截止",
    "竞品",
    "deadline",
    "risk",
    "remember",
    "retention",
    "review",
)


@dataclass(slots=True)
class TeamRetentionCandidate:
    memory: TeamRetentionMemory
    evidence_text: str
    signals: list[str]
    needs_review: bool = False

    def is_admissible(self, min_confidence: float = 0.45) -> bool:
        if not clean_text(self.memory.fact_value):
            return False
        return self.memory.confidence >= min_confidence


class TeamRetentionExtractor:
    """Rule-based extractor for team-retention memories."""

    def __init__(self, llm_client: Any | None = None, *, min_confidence: float = 0.45) -> None:
        self.llm_client = llm_client
        self.min_confidence = min_confidence

    def extract(self, event: NormalizedEvent) -> list[TeamRetentionCandidate]:
        text = self.collect_text(event)
        if not self.has_retention_signal(text, event.payload):
            return []
        candidate = self._extract_rule_based(text, context=event.context, event=event)
        if candidate.is_admissible(self.min_confidence):
            return [candidate]
        return []

    def collect_text(self, event: NormalizedEvent) -> str:
        parts: list[str] = []
        for value in (event.title, event.content_text):
            cleaned = clean_text(value)
            if cleaned:
                parts.append(cleaned)
        for key in ("text", "content", "message", "summary", "body", "fact_value"):
            value = event.payload.get(key)
            if isinstance(value, str) and clean_text(value):
                parts.append(clean_text(value))
        return clean_text(" ".join(dict.fromkeys(parts)))

    def has_retention_signal(self, text: str, payload: dict[str, Any]) -> bool:
        intent = payload.get("memory_intent") or payload.get("domain")
        if intent == "team_retention":
            return True
        lowered = text.lower()
        return any(keyword.lower() in lowered for keyword in RETENTION_KEYWORDS)

    def _extract_rule_based(
        self,
        text: str,
        *,
        context: EventContext,
        event: NormalizedEvent,
    ) -> TeamRetentionCandidate:
        payload = event.payload
        raw_fact_value = self._payload_str(payload, "fact_value") or self._infer_fact_value(text)
        fact_value = self._mask_secrets(raw_fact_value)
        fact_type = self._payload_str(payload, "fact_type") or self._infer_fact_type(text)
        risk_level = self._payload_str(payload, "risk_level") or self._infer_risk_level(text, fact_type)
        review_policy = self._payload_str(payload, "review_policy") or "ebbinghaus"
        owner = self._payload_str(payload, "owner")
        version_group = self._payload_str(payload, "version_group") or self._infer_version_group(
            fact_type,
            fact_value,
            context,
        )
        confidence = self._infer_confidence(text, payload)
        importance = self._infer_importance(risk_level)
        signals = [
            keyword
            for keyword in RETENTION_KEYWORDS
            if keyword.lower() in text.lower()
        ]
        memory = TeamRetentionMemory(
            team_id=context.team_id,
            project_id=context.project_id,
            workspace_id=context.workspace_id,
            thread_id=context.thread_id,
            fact_type=fact_type,  # type: ignore[arg-type]
            fact_value=fact_value,
            risk_level=risk_level,  # type: ignore[arg-type]
            owner=owner,
            remember_reason=self._payload_str(payload, "remember_reason"),
            review_policy=review_policy,  # type: ignore[arg-type]
            expiry_time=self._payload_str(payload, "expiry_time"),
            version_group=version_group,
            source_event_id=event.event_id,
            source_type=event.source_type,
            source_ref=self._source_ref(context, event),
            valid_from=event.occurred_at,
            tags=list(event.tags),
            confidence=confidence,
            importance=importance,
            created_at=event.occurred_at,
            metadata={
                "signals": signals,
                "source_payload_keys": sorted(payload.keys()),
                "secret_masked": fact_value != raw_fact_value,
            },
        )
        return TeamRetentionCandidate(
            memory=memory,
            evidence_text=text,
            signals=signals,
            needs_review=confidence < 0.65,
        )

    def _infer_fact_value(self, text: str) -> str:
        cleaned = clean_text(text)
        for marker in ("长期记住：", "长期记住:", "团队记住：", "团队记住:", "不要忘：", "不要忘:", "请记录：", "请记录:"):
            if marker in cleaned:
                return clean_text(cleaned.split(marker, 1)[1], max_chars=240)
        return clean_text(cleaned, max_chars=240)

    def _infer_fact_type(self, text: str) -> str:
        lowered = text.lower()
        if "api key" in lowered or "密钥" in text:
            return "api_key"
        if "客户" in text and any(term in text for term in ("要求", "偏好", "不接受", "接受")):
            return "customer_preference"
        if "竞品" in text or "competitor" in lowered:
            return "competitor_update"
        if "合规" in text or "compliance" in lowered:
            return "compliance"
        if "截止" in text or "deadline" in lowered:
            return "deadline"
        if "风险" in text or "risk" in lowered:
            return "risk"
        return "team_fact"

    def _infer_risk_level(self, text: str, fact_type: str) -> str:
        if fact_type in {"api_key", "compliance", "risk", "deadline"}:
            return "high"
        if fact_type in {"customer_preference", "competitor_update"}:
            return "medium"
        if any(term in text for term in ("严重", "必须", "禁止", "事故")):
            return "high"
        return "medium"

    def _infer_confidence(self, text: str, payload: dict[str, Any]) -> float:
        score = 0.5
        if payload.get("memory_intent") == "team_retention":
            score += 0.25
        if any(marker in text for marker in ("长期记住", "团队记住", "不要忘", "请记录")):
            score += 0.2
        if payload.get("fact_type") or payload.get("fact_value"):
            score += 0.1
        return min(score, 0.95)

    def _infer_importance(self, risk_level: str) -> float:
        return {"high": 0.9, "medium": 0.75, "low": 0.55}.get(risk_level, 0.7)

    def _infer_version_group(
        self,
        fact_type: str,
        fact_value: str,
        context: EventContext,
    ) -> str:
        scope = context.team_id or context.project_id or context.workspace_id or "global"
        topic = self._infer_version_topic(fact_value)
        return f"{scope}:{fact_type}:{topic}".lower()

    def _infer_version_topic(self, fact_value: str) -> str:
        customer_match = re.search(r"(客户|客戶)\s*([A-Za-z0-9_\-\u4e00-\u9fff]{1,12})", fact_value)
        if customer_match:
            tail = re.findall(r"导出|文件|密钥|key|合规|截止|竞品|偏好|要求", fact_value, flags=re.IGNORECASE)
            suffix = "-".join(tail[:2]) if tail else "general"
            return f"customer-{customer_match.group(2)}-{suffix}"
        key_terms = [
            term
            for term in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_\-]{2,}", fact_value)
            if term not in {"客户", "要求", "团队", "长期", "记住", "现在", "接受", "必须"}
        ]
        if key_terms:
            return "-".join(key_terms[:3])
        digest = hashlib.sha1(fact_value.encode("utf-8")).hexdigest()[:10]
        return f"fact-{digest}"

    def _mask_secrets(self, text: str) -> str:
        masked = text
        for pattern in SECRET_PATTERNS:
            if pattern.groups >= 3:
                masked = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", masked)
            else:
                masked = pattern.sub("[REDACTED]", masked)
        return masked

    def _source_ref(self, context: EventContext, event: NormalizedEvent) -> str:
        for key in ("source_ref", "message_id", "doc_id", "meeting_id"):
            value = event.payload.get(key)
            if isinstance(value, str) and clean_text(value):
                return clean_text(value)
        return context.thread_id or event.event_id

    def _payload_str(self, payload: dict[str, Any], key: str) -> str | None:
        value = payload.get(key)
        if isinstance(value, str) and clean_text(value):
            return clean_text(value)
        return None
