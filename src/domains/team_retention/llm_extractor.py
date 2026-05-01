from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any

from src.llm.base import LLMJSONDecodeError
from src.schemas import NormalizedEvent
from src.utils.text import clean_text

from .preprocessor import TeamRetentionPreprocessResult


@dataclass(slots=True)
class TeamRetentionLLMExtraction:
    """Structured semantic extraction result for one team_retention event."""

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
    certainty: str = "explicit"
    stability: str = "stable"
    actionability: str = "actionable"
    update_intent: str = "none"
    update_signal_text: str | None = None
    confirmation_reason: str | None = None
    needs_confirmation: bool = False
    reason: str | None = None
    evidence_text: str | None = None
    version_group_hint: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TeamRetentionLLMExtraction":
        """Create a normalized extraction object from model JSON."""
        candidate_flag = data.get("is_team_retention_candidate")
        is_memory = bool(data.get("is_team_retention_memory") if candidate_flag is None else candidate_flag)
        validity = data.get("validity") if isinstance(data.get("validity"), dict) else {}
        owner = data.get("owner")
        if owner is None:
            owner = data.get("owner_hint")
        risk_level = data.get("risk_level")
        if risk_level is None:
            risk_level = data.get("risk_level_hint")
        return cls(
            is_team_retention_memory=is_memory,
            fact_type=clean_text(str(data.get("fact_type") or "team_fact")),
            fact_value=clean_text(str(data.get("fact_value") or "")),
            summary=clean_text(data.get("summary")) or None,
            primary_entity=data.get("primary_entity") if isinstance(data.get("primary_entity"), dict) else {},
            topic_key=clean_text(data.get("topic_key")) or None,
            owner=clean_text(owner) or None,
            risk_level=clean_text(str(risk_level or "medium")),
            valid_from=clean_text(data.get("valid_from") or validity.get("valid_from")) or None,
            valid_to=clean_text(data.get("valid_to") or validity.get("valid_to")) or None,
            review_policy=clean_text(str(data.get("review_policy") or "ebbinghaus")),
            certainty=clean_text(str(data.get("certainty") or "explicit")),
            stability=clean_text(str(data.get("stability") or "stable")),
            actionability=clean_text(str(data.get("actionability") or "actionable")),
            update_intent=clean_text(str(data.get("update_intent") or "none")),
            update_signal_text=clean_text(data.get("update_signal_text")) or None,
            confirmation_reason=clean_text(data.get("confirmation_reason")) or None,
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
        "你是企业协作场景下的团队长期记忆抽取器。"
        "你只负责语义抽取、事实总结、证据摘取、不确定性说明和更新意图提示，"
        "不负责最终入库准入、active/candidate/reject 裁决、复习计划创建或覆盖旧记忆。"
        "不要输出重要性分数或最终状态；不要编造事件中没有的信息。"
        "如果信息是猜测、传闻、表达含糊或缺少来源，请标记 needs_confirmation。"
        "如果输入包含 [REDACTED]，请保留该标记，不要尝试还原；是否脱敏由后端策略决定。"
        "只返回 JSON，不要输出 Markdown、解释文字或额外字段。"
    )


def _user_prompt(event: NormalizedEvent, preprocess: TeamRetentionPreprocessResult) -> str:
    payload = {
        "context_hints": {
            "event_type": event.event_type,
            "source_type": event.source_type,
            "has_team_scope": bool(event.context.team_id),
            "has_project_scope": bool(event.context.project_id),
            "has_workspace_scope": bool(event.context.workspace_id),
            "sender_role_hint": "ordinary_member",
        },
        "text": preprocess.sanitized_text,
        "rule_features": {
            "description": "后端规则提取的弱提示，可能为空、不完整或有误。请优先根据 text 原文判断；如果 rule_features 与 text 冲突，以 text 为准。",
            **preprocess.features.to_dict(),
        },
        "task": "请抽取可能的团队长期记忆。不要打分，不要决定最终状态。",
        "allowed_values": {
            "fact_type": ["api_key", "customer_preference", "competitor_update", "compliance", "deadline", "risk", "team_fact"],
            "certainty": ["explicit", "inferred", "speculative"],
            "stability": ["stable", "temporary", "unknown"],
            "actionability": ["actionable", "informational", "unclear"],
            "risk_level_hint": ["low", "medium", "high"],
            "update_intent": ["none", "reinforce", "conflict", "supersede"],
        },
        "output_schema": {
            "is_team_retention_candidate": "boolean",
            "fact_type": "string",
            "fact_value": "string",
            "summary": "string",
            "primary_entity": {"type": "string", "name": "string", "normalized_key": "string"},
            "owner_hint": "string|null",
            "risk_level_hint": "low|medium|high",
            "validity": {"valid_from": "string|null", "valid_to": "string|null", "is_temporary": "boolean"},
            "certainty": "explicit|inferred|speculative",
            "stability": "stable|temporary|unknown",
            "actionability": "actionable|informational|unclear",
            "update_intent": "none|reinforce|conflict|supersede",
            "update_signal_text": "string|null",
            "needs_confirmation": "boolean",
            "confirmation_reason": "string|null",
            "evidence_text": "string",
            "reason": "string",
        },
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
            "is_team_retention_candidate": {"type": "boolean"},
            "fact_type": {"type": "string"},
            "fact_value": {"type": "string"},
            "summary": {"type": ["string", "null"]},
            "primary_entity": {"type": "object"},
            "topic_key": {"type": ["string", "null"]},
            "owner_hint": {"type": ["string", "null"]},
            "risk_level_hint": {"type": "string", "enum": ["low", "medium", "high"]},
            "validity": {"type": "object"},
            "certainty": {"type": "string", "enum": ["explicit", "inferred", "speculative"]},
            "stability": {"type": "string", "enum": ["stable", "temporary", "unknown"]},
            "actionability": {"type": "string", "enum": ["actionable", "informational", "unclear"]},
            "update_intent": {"type": "string", "enum": ["none", "reinforce", "conflict", "supersede"]},
            "update_signal_text": {"type": ["string", "null"]},
            "needs_confirmation": {"type": "boolean"},
            "confirmation_reason": {"type": ["string", "null"]},
            "reason": {"type": ["string", "null"]},
            "evidence_text": {"type": ["string", "null"]},
            "version_group_hint": {"type": ["string", "null"]},
        },
        "required": ["is_team_retention_candidate", "fact_type", "fact_value", "certainty", "stability", "actionability", "needs_confirmation", "evidence_text"],
    }

def _run_async(awaitable: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    raise RuntimeError("TeamRetentionLLMExtractor sync API cannot run inside an active event loop")
