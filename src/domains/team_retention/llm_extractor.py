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
        is_team = bool(data.get("is_team_retention", True))
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
        """
你是企业级长期记忆系统的 team_retention 抽取器。

输入事件已被路由到 team_retention。你的任务是从事件中抽取团队需要长期记住的事实，并标注证据质量、风险、影响范围和复习策略。只输出严格 JSON，不输出 Markdown、解释或额外字段。

关注的信息包括：
- API、接口、配置、鉴权、密钥、token、环境变量；
- 客户偏好、客户要求、客户禁忌；
- 竞品动态、市场变化、平台规则变化；
- 合规要求、安全规范、权限约束；
- 团队约定、项目背景、流程规范、系统设计约束；
- 风险、事故经验、故障教训、容易遗忘但会导致返工/错误/延期的信息；
- 截止时间、上线时间、交付节点；
- 新规则覆盖旧规则、版本更新、旧信息废弃。

字段填写规则：
- fact_type：api_key / customer_preference / competitor_update / compliance / deadline / risk / team_fact。
- fact_value：一句话写清核心事实，要求具体、可检索、不得编造。
- certainty：explicit 表示明确陈述；inferred 表示合理推断；speculative 表示猜测或未确认。
- evidence_quality：direct_quote 表示有直接原文；paraphrased 表示可转述；implied 表示主要靠上下文推断。
- fact_specificity：specific 表示对象/时间/约束/范围明确；general 表示信息较完整但缺细节；vague 表示模糊。
- risk_level：high / medium / low，表示遗忘后的风险。
- time_sensitivity：urgent / near_term / stable，表示时间敏感性。
- scope_impact：team_wide / project / individual，表示影响范围。
- irreversibility：irreversible / reversible / low_cost，表示遗忘或误用后的恢复成本。
- review_policy：ebbinghaus / fixed / none。长期易遗忘知识选 ebbinghaus；明确时间节点选 fixed；无需提醒选 none。
- evidence_text：支持 fact_value 的最小原文证据片段。
- reason：不超过 80 个中文字符；可为 null。
- summary：一句话记忆摘要；可为 null。
- primary_entity：格式为 {"name": string|null, "type": "customer|project|api|system|competitor|policy|team|person|unknown"}。
- topic_key：用于去重和归并的短字符串，如 payment_api_auth；不明确填 null。
- owner、valid_from、valid_to、version_group_hint：输入未明确则填 null。

判断优先级：
1. 密钥、token、鉴权优先归为 api_key。
2. 合规、安全、政策优先归为 compliance。
3. 客户要求优先归为 customer_preference。
4. 竞品或市场变化优先归为 competitor_update。
5. 明确时间节点优先归为 deadline。
6. 风险、事故、隐患优先归为 risk。
7. 其他团队长期事实归为 team_fact。

约束：
1. 只基于输入事件，不得臆造。
2. 输入信息较弱时，也要输出 JSON，并用 speculative / implied / vague / low / none 表示低质量。
3. 所有枚举必须严格使用规定值。
4. 时间优先用 YYYY-MM-DD；不明确填 null。
5. 只输出合法 JSON。
"""
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
            "certainty": {
                "type": "string",
                "enum": ["explicit", "inferred", "speculative"],
            },
            "evidence_quality": {
                "type": "string",
                "enum": ["direct_quote", "paraphrased", "implied"],
            },
            "fact_specificity": {
                "type": "string",
                "enum": ["specific", "general", "vague"],
            },
            "risk_level": {
                "type": "string",
                "enum": ["low", "medium", "high"],
            },
            "time_sensitivity": {
                "type": "string",
                "enum": ["urgent", "near_term", "stable"],
            },
            "scope_impact": {
                "type": "string",
                "enum": ["team_wide", "project", "individual"],
            },
            "irreversibility": {
                "type": "string",
                "enum": ["irreversible", "reversible", "low_cost"],
            },
            "review_policy": {
                "type": "string",
                "enum": ["ebbinghaus", "fixed", "none"],
            },
            "evidence_text": {"type": "string"},
            "reason": {"type": ["string", "null"]},
            "summary": {"type": ["string", "null"]},
            "primary_entity": {
                "type": "object",
                "properties": {
                    "name": {"type": ["string", "null"]},
                    "type": {
                        "type": "string",
                        "enum": [
                            "customer",
                            "project",
                            "api",
                            "system",
                            "competitor",
                            "policy",
                            "team",
                            "person",
                            "unknown",
                        ],
                    },
                },
                "required": ["name", "type"],
                "additionalProperties": False,
            },
            "topic_key": {"type": ["string", "null"]},
            "owner": {"type": ["string", "null"]},
            "valid_from": {"type": ["string", "null"]},
            "valid_to": {"type": ["string", "null"]},
            "version_group_hint": {"type": ["string", "null"]},
        },
        "required": [
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
        "additionalProperties": False,
    }


def _run_async(awaitable: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    raise RuntimeError("TeamRetentionLLMExtractor sync API cannot run inside an active event loop")
