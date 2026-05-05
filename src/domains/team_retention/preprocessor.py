from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from src.schemas import NormalizedEvent
from src.utils.text import clean_text

SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_\s-]*key|secret|token|password|passwd|pwd)(\s*[:=]\s*)([A-Za-z0-9_\-./+=]{6,})"),
    re.compile(r"\b(sk-[A-Za-z0-9_\-]{8,})\b"),
    re.compile(r"\b(AKIA[0-9A-Z]{12,})\b"),
)

SensitivePolicyMode = Literal["raw", "mask_for_llm", "mask_all"]


@dataclass(slots=True)
class TeamRetentionSensitivePolicy:
    mode: SensitivePolicyMode = "mask_for_llm"

    def text_for_llm(self, raw_text: str, masked_text: str) -> str:
        if self.mode == "raw":
            return raw_text
        return masked_text


@dataclass(slots=True)
class TeamRetentionPreprocessResult:
    raw_text: str
    sanitized_text: str


class TeamRetentionRulePreprocessor:
    """Collect text and mask secrets before LLM extraction."""

    def __init__(self, sensitive_policy: TeamRetentionSensitivePolicy | None = None) -> None:
        self.sensitive_policy = sensitive_policy or TeamRetentionSensitivePolicy()

    def preprocess(self, event: NormalizedEvent) -> TeamRetentionPreprocessResult:
        text = self._collect_text(event)
        masked = _mask_secrets(text)
        llm_text = self.sensitive_policy.text_for_llm(text, masked)
        return TeamRetentionPreprocessResult(raw_text=text, sanitized_text=llm_text)

    def _collect_text(self, event: NormalizedEvent) -> str:
        parts = [event.title, event.content_text]
        for key in ("text", "content", "message", "summary", "body", "fact_value"):
            value = event.payload.get(key)
            if isinstance(value, str):
                parts.append(value)
        return clean_text(" ".join(part for part in parts if part))


def _mask_secrets(text: str) -> str:
    masked = text
    for pattern in SECRET_PATTERNS:
        if pattern.groups >= 3:
            masked = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", masked)
        else:
            masked = pattern.sub("[REDACTED]", masked)
    return masked
