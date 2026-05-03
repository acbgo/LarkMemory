"""分析查询意图并决定主查与辅查领域。

委托统一的 DomainClassifier 做四域分类，
LLM 四标签纯文本输出 (temperature=0)，失败时降级到关键词规则。
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from ._types import IntentResult, MemoryDomain, RetrievalQuery

if TYPE_CHECKING:
    from src.core.domain_classifier import DomainClassifier
    from src.llm import LLMClient

logger = logging.getLogger(__name__)


def _extract_time_hint(text: str) -> str | None:
    if re.search(r"(最近|recently|刚才|just now|今天|today)", text):
        return "recent"
    if re.search(r"(上周|last\s*week|这周|this\s*week)", text):
        return "last_week"
    if re.search(r"(上个月|last\s*month|这个月|this\s*month)", text):
        return "last_month"
    return None


class IntentAnalyzer:

    def __init__(
        self,
        llm_client: "LLMClient | None" = None,
        *,
        classifier: "DomainClassifier | None" = None,
    ) -> None:
        if classifier is not None:
            self._classifier = classifier
        else:
            from src.core.domain_classifier import DomainClassifier
            self._classifier = DomainClassifier(llm_client=llm_client)

    async def analyze(self, query: RetrievalQuery) -> IntentResult:
        text = self._build_query_text(query)
        result = await self._classifier.classify(text, event_type=None)

        primary = [
            MemoryDomain(d) for d in result.primary
            if d in MemoryDomain.__members__.values()
        ]
        secondary = [
            MemoryDomain(d) for d in result.secondary
            if d in MemoryDomain.__members__.values() and d not in result.primary
        ]

        keywords = result.keywords if result.keywords else self._extract_keywords(query.query_text)
        if result.method == "llm" and primary:
            intent_type = primary[0].value
        elif result.method == "keyword_rule":
            intent_type = "keyword_matched"
        else:
            intent_type = result.method

        time_hint = _extract_time_hint(query.query_text.lower())

        return IntentResult(
            primary_domains=primary,
            secondary_domains=secondary,
            intent_type=intent_type,
            keywords=keywords,
            time_hint=time_hint,
            confidence=result.confidence,
        )

    @staticmethod
    def _build_query_text(query: RetrievalQuery) -> str:
        parts = [query.query_text]
        if query.project_id:
            parts.append(f"Project: {query.project_id}")
        if query.session_context:
            ctx_str = ", ".join(
                f"{k}={v}" for k, v in query.session_context.items()
            )
            parts.append(f"Context: {ctx_str}")
        return "\n".join(parts)

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        import re
        cleaned = text
        raw_terms = re.findall(r"[一-鿿]{2,}|[A-Za-z0-9_\-]{2,}", cleaned)
        stop_words = {"我们", "之前", "这个", "那个", "一下", "为什么", "帮我", "怎么"}
        result: list[str] = []
        for term in raw_terms:
            if term in stop_words or term.lower() in stop_words:
                continue
            if term not in result:
                result.append(term)
        return result[:10]
