from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from src.schemas import NormalizedEvent
from src.utils.text import clean_text

from .extractor import RETENTION_KEYWORDS, SECRET_PATTERNS


@dataclass(slots=True)
class TeamRetentionRuleFeatures:
    explicit_memory_keywords: list[str] = field(default_factory=list)
    risk_keywords: list[str] = field(default_factory=list)
    future_keywords: list[str] = field(default_factory=list)
    uncertainty_markers: list[str] = field(default_factory=list)
    update_markers: list[str] = field(default_factory=list)
    sensitive_detected: bool = False
    sensitive_masked: bool = False
    entity_hints: list[str] = field(default_factory=list)
    owner_hint: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation for prompts and metadata."""
        return {
            "explicit_memory_keywords": list(self.explicit_memory_keywords),
            "risk_keywords": list(self.risk_keywords),
            "future_keywords": list(self.future_keywords),
            "uncertainty_markers": list(self.uncertainty_markers),
            "update_markers": list(self.update_markers),
            "sensitive_detected": self.sensitive_detected,
            "sensitive_masked": self.sensitive_masked,
            "entity_hints": list(self.entity_hints),
            "owner_hint": self.owner_hint,
        }


@dataclass(slots=True)
class TeamRetentionPreprocessResult:
    raw_text: str
    sanitized_text: str
    features: TeamRetentionRuleFeatures


SensitivePolicyMode = Literal["raw", "mask_for_llm", "mask_all"]


@dataclass(slots=True)
class TeamRetentionSensitivePolicy:
    """Control whether sensitive values are preserved or masked for LLM input."""

    mode: SensitivePolicyMode = "mask_for_llm"

    def text_for_llm(self, raw_text: str, masked_text: str) -> str:
        """Return text that should be sent to the model under current policy."""
        if self.mode == "raw":
            return raw_text
        return masked_text


class TeamRetentionRulePreprocessor:
    """Build rule features and sanitize sensitive text before LLM extraction."""

    RISK_KEYWORDS = ("合规", "风险", "事故", "密钥", "token", "API key", "api key", "法务", "安全", "截止", "deadline")
    FUTURE_KEYWORDS = ("以后", "后续", "下次", "别再", "统一按", "必须", "禁止", "长期")
    UNCERTAINTY_KEYWORDS = ("可能", "应该", "感觉", "好像", "待确认", "回头确认", "不确定")
    UPDATE_KEYWORDS = ("现在", "改为", "更新为", "替换", "不再", "旧", "不用", "以后按", "废弃", "deprecated", "no longer")

    def __init__(self, sensitive_policy: TeamRetentionSensitivePolicy | None = None) -> None:
        self.sensitive_policy = sensitive_policy or TeamRetentionSensitivePolicy()

    def preprocess(self, event: NormalizedEvent) -> TeamRetentionPreprocessResult:
        """Collect text, mask secrets, and expose lightweight rule features."""
        text = self._collect_text(event)
        masked = self._mask_secrets(text)
        llm_text = self.sensitive_policy.text_for_llm(text, masked)
        lowered = llm_text.lower()
        features = TeamRetentionRuleFeatures(
            explicit_memory_keywords=[
                keyword
                for keyword in RETENTION_KEYWORDS
                if keyword.lower() in lowered
            ],
            risk_keywords=[
                keyword
                for keyword in self.RISK_KEYWORDS
                if keyword.lower() in lowered
            ],
            future_keywords=[
                keyword
                for keyword in self.FUTURE_KEYWORDS
                if keyword.lower() in lowered
            ],
            uncertainty_markers=[
                keyword
                for keyword in self.UNCERTAINTY_KEYWORDS
                if keyword.lower() in lowered
            ],
            update_markers=[
                keyword
                for keyword in self.UPDATE_KEYWORDS
                if keyword.lower() in lowered
            ],
            sensitive_detected=masked != text,
            sensitive_masked=llm_text != text,
            entity_hints=self._entity_hints(llm_text),
            owner_hint=self._owner_hint(llm_text),
        )
        return TeamRetentionPreprocessResult(raw_text=text, sanitized_text=llm_text, features=features)

    def _collect_text(self, event: NormalizedEvent) -> str:
        parts = [event.title, event.content_text]
        for key in ("text", "content", "message", "summary", "body", "fact_value"):
            value = event.payload.get(key)
            if isinstance(value, str):
                parts.append(value)
        return clean_text(" ".join(part for part in parts if part))

    def _mask_secrets(self, text: str) -> str:
        masked = text
        for pattern in SECRET_PATTERNS:
            if pattern.groups >= 3:
                masked = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", masked)
            else:
                masked = pattern.sub("[REDACTED]", masked)
        return masked

    def _entity_hints(self, text: str) -> list[str]:
        hints = re.findall(r"(?:客户|客戶)\s*([A-Za-z0-9_\-\u4e00-\u9fff]{1,12})", text)
        return [f"客户 {hint}" for hint in dict.fromkeys(hints)]

    def _owner_hint(self, text: str) -> str | None:
        match = re.search(r"(?:owner|负责人|由)\s*[:：]?\s*([A-Za-z0-9_\-\u4e00-\u9fff]{1,20})", text, re.IGNORECASE)
        return match.group(1) if match else None
