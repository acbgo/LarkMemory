"""补全主题、时间和上下文等检索信号。

接收原始查询和意图分析结果，通过规则 + 可选 LLM 增强，
输出包含 topic、时间窗口、scope filter 和 boost 信号的改写查询。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from ._types import (
    IntentResult,
    MemoryDomain,
    RetrievalQuery,
    RewrittenQuery,
    TimeWindow,
)

if TYPE_CHECKING:
    from src.llm import LLMClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM 查询改写 prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a query rewriter for a memory retrieval system.
Rewrite the user query into one clear search query for memory retrieval.

Only output the rewritten query. Do not output JSON, explanations, bullet points, or extra text.
"""

# ---------------------------------------------------------------------------
# 时间窗口推算规则
# ---------------------------------------------------------------------------

_TIME_HINT_WINDOWS: dict[str, timedelta] = {
    "recent": timedelta(days=3),
    "last_week": timedelta(weeks=1),
    "last_month": timedelta(days=30),
}


def _compute_time_window(
    time_hint: str | None,
    reference: datetime | None = None,
) -> TimeWindow | None:
    """根据意图分析得到的 time_hint 推算时间窗口。"""
    if not time_hint or time_hint not in _TIME_HINT_WINDOWS:
        return None
    ref = reference or datetime.now(timezone.utc)
    delta = _TIME_HINT_WINDOWS[time_hint]
    start = ref - delta
    return TimeWindow(
        start=start.isoformat(),
        end=ref.isoformat(),
        description=time_hint,
    )


# ---------------------------------------------------------------------------
# Scope filter 提取
# ---------------------------------------------------------------------------

def _extract_scope_filters(query: RetrievalQuery) -> dict[str, str]:
    """从查询上下文中提取 scope 级过滤条件。"""
    filters: dict[str, str] = {}
    if query.user_id:
        filters["user_id"] = query.user_id
    if query.project_id:
        filters["project_id"] = query.project_id
    if query.repo_id:
        filters["repo_id"] = query.repo_id
    if query.workspace_id:
        filters["workspace_id"] = query.workspace_id
    if query.team_id:
        filters["team_id"] = query.team_id
    return filters


# ---------------------------------------------------------------------------
# Boost 信号推算（规则策略）
# ---------------------------------------------------------------------------

_DOMAIN_DEFAULT_BOOSTS: dict[MemoryDomain, dict[str, float]] = {
    MemoryDomain.CLI_WORKFLOW: {
        "recency": 0.7,
        "frequency": 0.6,
        "success_rate": 0.5,
    },
    MemoryDomain.PROJECT_DECISION: {
        "recency": 0.4,
        "topic_match": 0.8,
        "version_latest": 0.7,
    },
    MemoryDomain.PERSONAL_PREFERENCE: {
        "confidence_score": 0.7,
        "recency": 0.3,
    },
    MemoryDomain.TEAM_RETENTION: {
        "risk_level": 0.8,
        "review_urgency": 0.6,
        "recency": 0.3,
    },
}


def _compute_boost_signals(
    intent: IntentResult,
    query: RetrievalQuery,
) -> dict[str, float]:
    """根据意图和上下文推算 boost 信号。"""
    boosts: dict[str, float] = {}

    if intent.primary_domains:
        primary = intent.primary_domains[0]
        boosts.update(_DOMAIN_DEFAULT_BOOSTS.get(primary, {}))

    if query.repo_id:
        boosts["repo_match"] = 0.8
    if query.project_id:
        boosts["project_match"] = 0.7

    return boosts


# ---------------------------------------------------------------------------
# 简易 topic 提取（规则策略）
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset({
    "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都",
    "一", "个", "上", "也", "么", "到", "说", "要", "去", "你", "会",
    "着", "没有", "看", "好", "自己", "这", "他", "她", "它", "们",
    "那", "被", "从", "把", "让", "用", "吗", "什么", "怎么", "如何",
    "哪", "为什么", "可以", "能", "请", "帮", "帮我",
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "can", "shall",
    "i", "you", "he", "she", "it", "we", "they", "me", "him",
    "her", "us", "them", "my", "your", "his", "its", "our", "their",
    "this", "that", "these", "those", "what", "which", "who", "how",
    "when", "where", "why", "and", "or", "but", "in", "on", "at",
    "to", "for", "of", "with", "by", "from", "as", "into", "about",
})

_DOMAIN_TOPIC_TERMS = (
    "openclaw", "飞书", "lark", "memory", "hook", "agent", "llm",
    "插件", "记忆", "检索", "注入", "上下文", "机器人",
    "部署", "构建", "排障", "命令", "脚本", "终端",
    "决策", "方案", "选型", "架构", "理由", "权衡",
    "偏好", "习惯", "默认", "风格",
    "团队", "提醒", "合规", "风险", "截止", "复习",
)


def _extract_topics_by_rules(text: str) -> list[str]:
    """通过分词和停用词过滤提取粗粒度 topic。"""
    lower_text = text.lower()
    tokens = re.findall(r"[a-zA-Z0-9][\w\-\.]*", lower_text)
    topics = [t for t in tokens if t not in _STOPWORDS and len(t) > 1]

    for term in _DOMAIN_TOPIC_TERMS:
        if term.lower() in lower_text:
            topics.append(term)

    seen: set[str] = set()
    deduped: list[str] = []
    for t in topics:
        key = t.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(t)
    return deduped[:15]


def _clean_rewritten_text(text: str) -> str:
    """清理 LLM 纯文本改写结果，只保留第一条可用检索语句。"""
    cleaned_lines = [
        line.strip().strip("\"'`")
        for line in text.splitlines()
        if line.strip()
    ]
    return cleaned_lines[0] if cleaned_lines else ""


# ---------------------------------------------------------------------------
# QueryRewriter
# ---------------------------------------------------------------------------

class QueryRewriter:
    """补全检索信号，输出改写后的查询。

    Parameters
    ----------
    llm_client:
        LLMClient 实例。传 None 则使用纯规则策略。
    """

    def __init__(self, llm_client: "LLMClient | None" = None) -> None:
        """初始化查询改写器，输入可选 LLMClient；未传入时使用规则策略。"""
        self._llm = llm_client

    async def rewrite(
        self,
        query: RetrievalQuery,
        intent: IntentResult,
    ) -> RewrittenQuery:
        """改写查询，补全检索信号。优先 LLM，失败降级到规则。"""
        scope_filters = _extract_scope_filters(query)

        if self._llm is not None:
            try:
                return await self._rewrite_with_llm(
                    query, intent, scope_filters,
                )
            except Exception:
                logger.warning(
                    "LLM query rewrite failed, falling back to rules",
                    exc_info=True,
                )

        return self._rewrite_by_rules(query, intent, scope_filters)

    # ------------------------------------------------------------------
    # LLM 策略
    # ------------------------------------------------------------------

    async def _rewrite_with_llm(
        self,
        query: RetrievalQuery,
        intent: IntentResult,
        scope_filters: dict[str, str],
    ) -> RewrittenQuery:
        """调用 LLM 只生成改写语句，其余检索信号由规则补齐。"""
        user_prompt = self._build_user_prompt(query, intent)
        rewritten_text = await self._llm.atext(
            _SYSTEM_PROMPT,
            user_prompt,
            temperature=0,
        )

        result = self._rewrite_by_rules(query, intent, scope_filters)
        cleaned = _clean_rewritten_text(rewritten_text)
        if cleaned:
            result.rewritten_text = cleaned
        return result

    # ------------------------------------------------------------------
    # 规则策略
    # ------------------------------------------------------------------

    def _rewrite_by_rules(
        self,
        query: RetrievalQuery,
        intent: IntentResult,
        scope_filters: dict[str, str],
    ) -> RewrittenQuery:
        topics = _extract_topics_by_rules(query.query_text)
        if intent.keywords:
            for kw in intent.keywords:
                if kw.lower() not in {t.lower() for t in topics}:
                    topics.append(kw)

        time_window = _compute_time_window(intent.time_hint)
        boosts = _compute_boost_signals(intent, query)

        return RewrittenQuery(
            original=query,
            rewritten_text=query.query_text,
            extracted_topics=topics,
            time_window=time_window,
            scope_filters=scope_filters,
            boost_signals=boosts,
        )

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    @staticmethod
    def _build_user_prompt(
        query: RetrievalQuery,
        intent: IntentResult,
    ) -> str:
        parts = [
            f"Original query: {query.query_text}",
            f"Detected intent: {intent.intent_type}",
            f"Primary domains: {[d.value for d in intent.primary_domains]}",
        ]
        if intent.keywords:
            parts.append(f"Keywords: {intent.keywords}")
        if intent.time_hint:
            parts.append(f"Time hint: {intent.time_hint}")
        if query.project_id:
            parts.append(f"Project: {query.project_id}")
        if query.repo_id:
            parts.append(f"Repo: {query.repo_id}")
        if query.session_context:
            ctx_str = ", ".join(
                f"{k}={v}" for k, v in query.session_context.items()
            )
            parts.append(f"Session context: {ctx_str}")
        return "\n".join(parts)
