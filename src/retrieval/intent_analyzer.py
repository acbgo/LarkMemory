"""分析查询意图并决定主查与辅查领域。

通过 LLM 结构化输出判断用户查询属于哪个记忆领域，
当 LLM 不可用时降级到基于关键词的规则匹配。
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from ._types import IntentResult, MemoryDomain, RetrievalQuery

if TYPE_CHECKING:
    from src.llm import LLMClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM 意图分析 prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an intent classifier for a memory retrieval system.
Given a user query and optional context, determine which memory domains are relevant.

Available domains:
- cli_workflow: CLI commands, deployment, build, troubleshooting, shell operations
- project_decision: project decisions, rationale, alternatives, why something was chosen
- personal_preference: user habits, preferences, routines, personalized defaults
- team_retention: team critical facts, reminders, compliance rules, review schedules

Respond with a JSON object:
{
  "primary_domains": ["<domain>", ...],
  "secondary_domains": ["<domain>", ...],
  "intent_type": "<short label>",
  "keywords": ["<keyword>", ...],
  "time_hint": "<recent | last_week | last_month | null>",
  "confidence": <0.0-1.0>
}

Rules:
- primary_domains: 1-2 domains most relevant to the query (never empty)
- secondary_domains: 0-2 domains that may provide supplementary info
- A domain should not appear in both primary and secondary
- intent_type: a short English label like "deployment", "decision_lookup", "preference", "reminder", "general"
- time_hint: if the query implies a time range, specify it; otherwise null
- confidence: how confident you are in the classification
"""

_INTENT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "primary_domains": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [d.value for d in MemoryDomain],
            },
        },
        "secondary_domains": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [d.value for d in MemoryDomain],
            },
        },
        "intent_type": {"type": "string"},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "time_hint": {"type": ["string", "null"]},
        "confidence": {"type": "number"},
    },
    "required": [
        "primary_domains",
        "secondary_domains",
        "intent_type",
        "keywords",
        "confidence",
    ],
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# 关键词降级规则
# ---------------------------------------------------------------------------

_KEYWORD_RULES: list[tuple[list[str], MemoryDomain]] = [
    # cli_workflow
    (
        [
            "部署", "deploy", "构建", "build", "运行", "run", "命令",
            "command", "shell", "终端", "terminal", "排障", "debug",
            "脚本", "script", "pipeline", "ci", "cd", "docker",
            "kubectl", "npm", "pip", "git",
        ],
        MemoryDomain.CLI_WORKFLOW,
    ),
    # project_decision
    (
        [
            "决策", "decision", "为什么", "why", "方案", "选型", "架构",
            "architecture", "选择", "choose", "理由", "rationale",
            "替代", "alternative", "权衡", "trade-off", "tradeoff",
            "设计", "design", "技术栈", "tech stack",
        ],
        MemoryDomain.PROJECT_DECISION,
    ),
    # personal_preference
    (
        [
            "偏好", "preference", "习惯", "habit", "默认", "default",
            "喜欢", "prefer", "平时", "usually", "风格", "style",
            "个人", "personal", "routine", "例行",
        ],
        MemoryDomain.PERSONAL_PREFERENCE,
    ),
    # team_retention
    (
        [
            "提醒", "remind", "团队", "team", "关键", "critical",
            "合规", "compliance", "过期", "expir", "复习", "review",
            "风险", "risk", "api key", "截止", "deadline", "遗忘",
            "forget", "保留", "retain",
        ],
        MemoryDomain.TEAM_RETENTION,
    ),
]

# 辅查关联规则：当主查为某域时，哪些域适合做辅查
_SECONDARY_AFFINITY: dict[MemoryDomain, list[MemoryDomain]] = {
    MemoryDomain.CLI_WORKFLOW: [MemoryDomain.TEAM_RETENTION],
    MemoryDomain.PROJECT_DECISION: [MemoryDomain.TEAM_RETENTION],
    MemoryDomain.PERSONAL_PREFERENCE: [],
    MemoryDomain.TEAM_RETENTION: [MemoryDomain.PROJECT_DECISION],
}


def _keyword_fallback(query: RetrievalQuery) -> IntentResult:
    """基于关键词规则的意图匹配降级策略。"""
    text = query.query_text.lower()
    domain_scores: dict[MemoryDomain, int] = {d: 0 for d in MemoryDomain}

    for keywords, domain in _KEYWORD_RULES:
        for kw in keywords:
            if kw.lower() in text:
                domain_scores[domain] += 1

    ranked = sorted(domain_scores.items(), key=lambda x: x[1], reverse=True)
    primary: list[MemoryDomain] = []
    secondary: list[MemoryDomain] = []

    if ranked[0][1] > 0:
        primary.append(ranked[0][0])
        if ranked[1][1] > 0 and ranked[1][1] >= ranked[0][1] * 0.5:
            primary.append(ranked[1][0])
    else:
        primary.append(MemoryDomain.TEAM_RETENTION)
        secondary.append(MemoryDomain.PROJECT_DECISION)

    if len(primary) == 1 and not secondary:
        secondary = [
            d for d in _SECONDARY_AFFINITY.get(primary[0], [])
            if d not in primary
        ]

    matched = [kw for kws, _ in _KEYWORD_RULES for kw in kws if kw.lower() in text]

    time_hint = _extract_time_hint(text)

    max_score = ranked[0][1] if ranked[0][1] > 0 else 0
    confidence = min(0.3 + max_score * 0.1, 0.8)

    return IntentResult(
        primary_domains=primary,
        secondary_domains=secondary,
        intent_type="keyword_matched",
        keywords=matched[:10],
        time_hint=time_hint,
        confidence=confidence,
    )


def _extract_time_hint(text: str) -> str | None:
    """从查询文本中提取粗粒度时间提示，返回 recent/last_week/last_month 或 None。"""
    if re.search(r"(最近|recently|刚才|just now|今天|today)", text):
        return "recent"
    if re.search(r"(上周|last\s*week|这周|this\s*week)", text):
        return "last_week"
    if re.search(r"(上个月|last\s*month|这个月|this\s*month)", text):
        return "last_month"
    return None


# ---------------------------------------------------------------------------
# IntentAnalyzer
# ---------------------------------------------------------------------------

class IntentAnalyzer:
    """分析查询意图，决定主查与辅查领域。

    Parameters
    ----------
    llm_client:
        LLMClient 实例。传 None 则始终使用关键词降级策略。
    """

    def __init__(self, llm_client: "LLMClient | None" = None) -> None:
        """初始化意图分析器，输入可选 LLMClient；未传入时使用关键词规则。"""
        self._llm = llm_client

    async def analyze(self, query: RetrievalQuery) -> IntentResult:
        """分析查询意图。优先使用 LLM，失败时降级到关键词规则。"""
        if self._llm is not None:
            try:
                return await self._analyze_with_llm(query)
            except Exception:
                logger.warning(
                    "LLM intent analysis failed, falling back to keyword rules",
                    exc_info=True,
                )
        return _keyword_fallback(query)

    async def _analyze_with_llm(self, query: RetrievalQuery) -> IntentResult:
        """调用 LLM 进行意图分类，输入检索查询并返回解析后的 IntentResult。"""
        user_prompt = self._build_user_prompt(query)
        raw: dict[str, Any] = await self._llm.ajson(
            _SYSTEM_PROMPT,
            user_prompt,
            schema=_INTENT_JSON_SCHEMA,
            temperature=0,
        )
        return self._parse_llm_output(raw)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _build_user_prompt(query: RetrievalQuery) -> str:
        """将 RetrievalQuery 构造成 LLM 用户提示，包含查询文本和可用上下文。"""
        parts = [f"Query: {query.query_text}"]
        if query.project_id:
            parts.append(f"Project: {query.project_id}")
        if query.repo_id:
            parts.append(f"Repo: {query.repo_id}")
        if query.session_context:
            ctx_str = ", ".join(
                f"{k}={v}" for k, v in query.session_context.items()
            )
            parts.append(f"Context: {ctx_str}")
        return "\n".join(parts)

    @staticmethod
    def _parse_llm_output(raw: dict[str, Any]) -> IntentResult:
        """解析 LLM JSON 输出，过滤非法领域并补齐默认主查/辅查领域。"""
        primary = [
            MemoryDomain(d) for d in raw.get("primary_domains", [])
            if d in {m.value for m in MemoryDomain}
        ]
        secondary = [
            MemoryDomain(d) for d in raw.get("secondary_domains", [])
            if d in {m.value for m in MemoryDomain}
        ]
        if not primary:
            primary = [MemoryDomain.TEAM_RETENTION]

        secondary = [d for d in secondary if d not in primary]
        if not secondary and primary == [MemoryDomain.TEAM_RETENTION]:
            secondary = [MemoryDomain.PROJECT_DECISION]

        return IntentResult(
            primary_domains=primary,
            secondary_domains=secondary,
            intent_type=raw.get("intent_type", "general"),
            keywords=raw.get("keywords", []),
            time_hint=raw.get("time_hint"),
            confidence=float(raw.get("confidence", 0.5)),
        )
