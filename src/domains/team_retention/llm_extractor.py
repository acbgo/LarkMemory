from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from src.llm.base import LLMJSONDecodeError
from src.schemas import NormalizedEvent
from src.utils.text import clean_text

from .preprocessor import TeamRetentionPreprocessResult


TeamRetentionLLMDecision = Literal["reject", "candidate", "active"]


@dataclass(slots=True)
class TeamRetentionLLMExtraction:
    """Structured LLM result for one team_retention extraction decision."""

    decision: TeamRetentionLLMDecision
    is_team_retention_memory: bool
    fact_type: str = "team_fact"
    fact_value: str = ""
    summary: str | None = None
    primary_entity: dict[str, Any] = field(default_factory=dict)
    topic_key: str | None = None
    owner: str | None = None
    risk_level: str = "medium"
    valid_from: str | None = None
    valid_to: str | None = None
    review_policy: str = "ebbinghaus"
    confidence: float = 0.0
    importance: float = 0.0
    score_breakdown: dict[str, float] = field(default_factory=dict)
    needs_confirmation: bool = False
    reason: str | None = None
    evidence_text: str | None = None
    version_group_hint: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TeamRetentionLLMExtraction":
        """Create a normalized extraction object from model JSON."""
        decision = str(data.get("decision") or "reject")
        if decision not in {"reject", "candidate", "active"}:
            decision = "reject"
        return cls(
            decision=decision,  # type: ignore[arg-type]
            is_team_retention_memory=bool(data.get("is_team_retention_memory")),
            fact_type=clean_text(str(data.get("fact_type") or "team_fact")),
            fact_value=clean_text(str(data.get("fact_value") or "")),
            summary=clean_text(data.get("summary")) or None,
            primary_entity=data.get("primary_entity") if isinstance(data.get("primary_entity"), dict) else {},
            topic_key=clean_text(data.get("topic_key")) or None,
            owner=clean_text(data.get("owner")) or None,
            risk_level=clean_text(str(data.get("risk_level") or "medium")),
            valid_from=clean_text(data.get("valid_from")) or None,
            valid_to=clean_text(data.get("valid_to")) or None,
            review_policy=clean_text(str(data.get("review_policy") or "ebbinghaus")),
            confidence=_clamp(data.get("confidence") or 0.0),
            importance=_clamp(data.get("importance") or 0.0),
            score_breakdown=_score_breakdown(data.get("score_breakdown")),
            needs_confirmation=bool(data.get("needs_confirmation")),
            reason=clean_text(data.get("reason")) or None,
            evidence_text=clean_text(data.get("evidence_text")) or None,
            version_group_hint=clean_text(data.get("version_group_hint")) or None,
        )


class TeamRetentionLLMExtractor:
    """Call the shared LLMClient once to classify and extract team retention memory."""

    def __init__(self, llm_client: Any, *, max_tokens: int = 900) -> None:
        self.llm_client = llm_client
        self.max_tokens = max_tokens

    def extract(
        self,
        event: NormalizedEvent,
        preprocess: TeamRetentionPreprocessResult,
    ) -> TeamRetentionLLMExtraction | None:
        """Synchronously run the async JSON extraction helper for current handler flow."""
        try:
            return _run_async(self.extract_async(event, preprocess))
        except (LLMJSONDecodeError, RuntimeError, ValueError):
            return None

    async def extract_async(
        self,
        event: NormalizedEvent,
        preprocess: TeamRetentionPreprocessResult,
    ) -> TeamRetentionLLMExtraction:
        """Return a structured extraction from one LLM JSON call."""
        data = await self.llm_client.ajson(
            _system_prompt(),
            _user_prompt(event, preprocess),
            schema=_json_schema(),
            temperature=0,
            max_tokens=self.max_tokens,
        )
        return TeamRetentionLLMExtraction.from_dict(data)


def _system_prompt() -> str:
    return (
        "You extract enterprise team-retention memories from normalized events. "
        "Return JSON only. Decide whether the event is reject, candidate, or active. "
        "candidate means retrievable but not proactively reminded. active means retrievable and eligible for review reminders. "
        "Do not preserve raw secrets; use redacted text when sensitive values appear."
    )


def _user_prompt(event: NormalizedEvent, preprocess: TeamRetentionPreprocessResult) -> str:
    payload = {
        "event": {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "source_type": event.source_type,
            "occurred_at": event.occurred_at,
            "context": {
                "team_id": event.context.team_id,
                "project_id": event.context.project_id,
                "workspace_id": event.context.workspace_id,
                "thread_id": event.context.thread_id,
            },
            "content_text": preprocess.sanitized_text,
            "tags": event.tags,
            "payload": _sanitize_payload(event.payload),
        },
        "rule_features": preprocess.features.to_dict(),
        "rubric": {
            "active": "Long-term team fact, clear scope, clear fact, enough confidence, no unmasked sensitive value.",
            "candidate": "Possibly valuable team memory but uncertain, incomplete, sensitive-but-masked, or needs confirmation.",
            "reject": "Ordinary chat/status/personal preference/short-lived task/no stable team fact.",
        },
        "score_fields": [
            "explicit_intent",
            "future_dependency",
            "cross_member_dependency",
            "risk_or_cost",
            "source_authority",
            "stability",
            "actionability",
            "uncertainty_penalty",
            "sensitivity_penalty",
            "triviality_penalty",
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, str):
        return _mask_secrets(value)
    if isinstance(value, dict):
        return {str(key): _sanitize_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


def _mask_secrets(text: str) -> str:
    patterns = (
        re.compile(r"(?i)(api[_\s-]*key|secret|token|password|passwd|pwd)(\s*[:=]\s*)([A-Za-z0-9_\-./+=]{6,})"),
        re.compile(r"\b(sk-[A-Za-z0-9_\-]{8,})\b"),
        re.compile(r"\b(AKIA[0-9A-Z]{12,})\b"),
    )
    masked = text
    for pattern in patterns:
        if pattern.groups >= 3:
            masked = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", masked)
        else:
            masked = pattern.sub("[REDACTED]", masked)
    return masked


def _json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["reject", "candidate", "active"]},
            "is_team_retention_memory": {"type": "boolean"},
            "fact_type": {"type": "string"},
            "fact_value": {"type": "string"},
            "summary": {"type": ["string", "null"]},
            "primary_entity": {"type": "object"},
            "topic_key": {"type": ["string", "null"]},
            "owner": {"type": ["string", "null"]},
            "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
            "valid_from": {"type": ["string", "null"]},
            "valid_to": {"type": ["string", "null"]},
            "review_policy": {"type": "string", "enum": ["ebbinghaus", "fixed", "none"]},
            "confidence": {"type": "number"},
            "importance": {"type": "number"},
            "score_breakdown": {"type": "object"},
            "needs_confirmation": {"type": "boolean"},
            "reason": {"type": ["string", "null"]},
            "evidence_text": {"type": ["string", "null"]},
            "version_group_hint": {"type": ["string", "null"]},
        },
        "required": ["decision", "is_team_retention_memory", "score_breakdown"],
    }


def _score_breakdown(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _clamp(raw) for key, raw in value.items() if isinstance(raw, (int, float))}


def _clamp(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def _run_async(awaitable: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    raise RuntimeError("TeamRetentionLLMExtractor sync API cannot run inside an active event loop")
