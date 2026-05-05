from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from src.llm.base import LLMJSONDecodeError
from src.schemas import NormalizedEvent
from src.utils.text import clean_text

from .preprocessor import TeamRetentionPreprocessResult


@dataclass(slots=True)
class TeamRetentionLLMExtraction:
    is_team_retention: bool
    fact_type: str = "team_fact"
    fact_value: str = ""
    certainty: str = "inferred"
    evidence_quality: str = "paraphrased"
    fact_specificity: str = "general"
    risk_level: str = "medium"
    time_sensitivity: str = "stable"
    scope_impact: str = "project"
    irreversibility: str = "reversible"
    review_policy: str = "ebbinghaus"
    evidence_text: str = ""
    reason: str | None = None
    summary: str | None = None
    primary_entity: dict[str, Any] = field(default_factory=dict)
    topic_key: str | None = None
    owner: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    version_group_hint: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TeamRetentionLLMExtraction":
        candidate_flag = data.get("is_team_retention_candidate")
        is_team = bool(data.get("is_team_retention") if candidate_flag is None else candidate_flag)
        return cls(
            is_team_retention=is_team,
            fact_type=clean_text(str(data.get("fact_type") or "team_fact")),
            fact_value=clean_text(str(data.get("fact_value") or "")),
            certainty=clean_text(str(data.get("certainty") or "inferred")),
            evidence_quality=clean_text(str(data.get("evidence_quality") or "paraphrased")),
            fact_specificity=clean_text(str(data.get("fact_specificity") or "general")),
            risk_level=clean_text(str(data.get("risk_level") or data.get("risk_level_hint") or "medium")),
            time_sensitivity=clean_text(str(data.get("time_sensitivity") or "stable")),
            scope_impact=clean_text(str(data.get("scope_impact") or "project")),
            irreversibility=clean_text(str(data.get("irreversibility") or "reversible")),
            review_policy=clean_text(str(data.get("review_policy") or "ebbinghaus")),
            evidence_text=clean_text(str(data.get("evidence_text") or "")),
            reason=clean_text(data.get("reason")) or None,
            summary=clean_text(data.get("summary")) or None,
            primary_entity=data.get("primary_entity") if isinstance(data.get("primary_entity"), dict) else {},
            topic_key=clean_text(data.get("topic_key")) or None,
            owner=clean_text(data.get("owner") or data.get("owner_hint")) or None,
            valid_from=clean_text(data.get("valid_from")) or None,
            valid_to=clean_text(data.get("valid_to")) or None,
            version_group_hint=clean_text(data.get("version_group_hint")) or None,
        )


class TeamRetentionLLMExtractor:
    def __init__(self, llm_client: Any, *, max_tokens: int = 900) -> None:
        self.llm_client = llm_client
        self.max_tokens = max_tokens

    def extract(
        self,
        event: NormalizedEvent,
        preprocess: TeamRetentionPreprocessResult,
    ) -> TeamRetentionLLMExtraction | None:
        try:
            return _run_async(self.extract_async(event, preprocess))
        except (LLMJSONDecodeError, RuntimeError, ValueError):
            return None

    async def extract_async(
        self,
        event: NormalizedEvent,
        preprocess: TeamRetentionPreprocessResult,
    ) -> TeamRetentionLLMExtraction:
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
        "你是团队长期记忆抽取器。从事件文本中提取需要团队长期记住的关键事实。"
        "对每条事实，你必须给出以下定性判断（不要输出数值分数）：\n"
        "- certainty: explicit（明确陈述）/ inferred（可从上下文推断）/ speculative（猜测或传闻）\n"
        "- evidence_quality: direct_quote（原文直接引用）/ paraphrased（转述原文内容）/ implied（隐含在上下文中）\n"
        "- fact_specificity: specific（包含具体值或明确指令）/ general（一般性描述）/ vague（模糊提及）\n"
        "- risk_level: high（安全/合规/法律风险）/ medium（业务影响）/ low（仅供参考）\n"
        "- time_sensitivity: urgent（需立即处理）/ near_term（近期相关）/ stable（长期不变）\n"
        "- scope_impact: team_wide（影响全团队）/ project（影响单个项目）/ individual（影响个人）\n"
        "- irreversibility: irreversible（不可逆操作）/ reversible（可撤销）/ low_cost（低代价）\n\n"
        "判断标准:\n"
        "- 如果信息是猜测、传闻或含糊不清 → certainty=speculative, evidence_quality=implied\n"
        "- 如果信息明确、有具体值且可追溯 → certainty=explicit, evidence_quality=direct_quote\n"
        "- 如果你不确定是否为团队知识 → is_team_retention=false\n"
        "- 如果输入包含 [REDACTED]，保留该标记，不要尝试还原\n"
        "只返回 JSON，不要输出 Markdown、解释文字或额外字段。"
    )


def _user_prompt(event: NormalizedEvent, preprocess: TeamRetentionPreprocessResult) -> str:
    return json.dumps(
        {
            "context": {
                "event_type": event.event_type,
                "source_type": event.source_type,
                "has_team_scope": bool(event.context.team_id),
                "has_project_scope": bool(event.context.project_id),
            },
            "text": preprocess.sanitized_text,
        },
        ensure_ascii=False,
    )


def _json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "is_team_retention": {"type": "boolean"},
            "fact_type": {
                "type": "string",
                "enum": [
                    "api_key",
                    "customer_preference",
                    "competitor_update",
                    "compliance",
                    "deadline",
                    "risk",
                    "team_fact",
                ],
            },
            "fact_value": {"type": "string"},
            "certainty": {"type": "string", "enum": ["explicit", "inferred", "speculative"]},
            "evidence_quality": {"type": "string", "enum": ["direct_quote", "paraphrased", "implied"]},
            "fact_specificity": {"type": "string", "enum": ["specific", "general", "vague"]},
            "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
            "time_sensitivity": {"type": "string", "enum": ["urgent", "near_term", "stable"]},
            "scope_impact": {"type": "string", "enum": ["team_wide", "project", "individual"]},
            "irreversibility": {"type": "string", "enum": ["irreversible", "reversible", "low_cost"]},
            "review_policy": {"type": "string", "enum": ["ebbinghaus", "fixed", "none"]},
            "evidence_text": {"type": "string"},
            "reason": {"type": ["string", "null"]},
            "summary": {"type": ["string", "null"]},
            "primary_entity": {"type": "object"},
            "topic_key": {"type": ["string", "null"]},
            "owner": {"type": ["string", "null"]},
            "valid_from": {"type": ["string", "null"]},
            "valid_to": {"type": ["string", "null"]},
            "version_group_hint": {"type": ["string", "null"]},
        },
        "required": [
            "is_team_retention",
            "fact_type",
            "fact_value",
            "certainty",
            "evidence_quality",
            "fact_specificity",
            "risk_level",
            "time_sensitivity",
            "scope_impact",
            "irreversibility",
            "evidence_text",
        ],
    }


def _run_async(awaitable: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    raise RuntimeError("TeamRetentionLLMExtractor sync API cannot run inside an active event loop")
