"""对跨领域结果做统一重排。

支持两种策略：
1. 轻量策略 —— 多因子加权打分（无需 LLM）
2. 重量策略 —— 调用 LLM 做 listwise 语义重排（可选）
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from ._types import (
    FusedCandidate,
    MemoryDomain,
    MemoryScope,
    RankedMemory,
    RewrittenQuery,
)

if TYPE_CHECKING:
    from src.llm import LLMClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 因子权重默认值
# ---------------------------------------------------------------------------

DEFAULT_FACTOR_WEIGHTS: dict[str, float] = {
    "fusion": 0.30,
    "importance": 0.20,
    "confidence": 0.15,
    "freshness": 0.15,
    "topic_overlap": 0.10,
    "scope_match": 0.10,
}

# 每个域可以覆盖默认因子权重
_DOMAIN_WEIGHT_OVERRIDES: dict[MemoryDomain, dict[str, float]] = {
    MemoryDomain.CLI_WORKFLOW: {
        "freshness": 0.25,
        "importance": 0.10,
    },
    MemoryDomain.PROJECT_DECISION: {
        "topic_overlap": 0.20,
        "freshness": 0.05,
    },
    MemoryDomain.TEAM_RETENTION: {
        "importance": 0.30,
        "freshness": 0.05,
    },
}

# LLM 重排 prompt
_RERANK_SYSTEM_PROMPT = """\
You are a relevance judge for a memory retrieval system.
Given a user query and a list of memory candidates, rank them by relevance.

Respond with a JSON object:
{
  "ranked_ids": ["<memory_id_1>", "<memory_id_2>", ...]
}

Put the most relevant memory first. Include ALL provided memory IDs.
"""

_RERANK_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ranked_ids": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["ranked_ids"],
    "additionalProperties": False,
}

# LLM 重排只取前 N 个候选，避免 prompt 过长
_LLM_RERANK_WINDOW = 20


# ---------------------------------------------------------------------------
# 因子计算
# ---------------------------------------------------------------------------

def _score_fusion(candidate: FusedCandidate) -> float:
    """fusion_score 已在 fusion 阶段计算，归一化到 [0, 1]。"""
    return min(candidate.fusion_score * 60, 1.0)


def _score_importance(candidate: FusedCandidate) -> float:
    return candidate.item.importance


def _score_confidence(candidate: FusedCandidate) -> float:
    return candidate.item.confidence


def _score_freshness(candidate: FusedCandidate) -> float:
    """基于 updated_at 的时间衰减，越新越高。"""
    if candidate.item.freshness_score is not None:
        return candidate.item.freshness_score

    updated = candidate.item.updated_at or candidate.item.created_at
    if not updated:
        return 0.3

    try:
        dt = datetime.fromisoformat(updated)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        days_old = max((now - dt).total_seconds() / 86400, 0)
        # 半衰期 30 天
        return math.exp(-0.693 * days_old / 30)
    except (ValueError, TypeError):
        return 0.3


def _score_topic_overlap(
    candidate: FusedCandidate,
    query: RewrittenQuery,
) -> float:
    """查询 topic 与记忆 tags/entities 的重叠度。"""
    if not query.extracted_topics:
        return 0.0

    query_topics = {t.lower() for t in query.extracted_topics}
    item_terms = {
        t.lower()
        for t in (candidate.item.tags + candidate.item.entities)
    }
    content_lower = candidate.item.content_text.lower()
    item_terms.update(
        t for t in query_topics if t in content_lower
    )

    if not item_terms:
        return 0.0

    overlap = len(query_topics & item_terms)
    return overlap / len(query_topics)


def _score_scope_match(
    candidate: FusedCandidate,
    query: RewrittenQuery,
) -> float:
    """scope filter 匹配度。"""
    if not query.scope_filters:
        return 0.5

    extra = candidate.item.extra
    matched = 0
    total = len(query.scope_filters)

    for key, value in query.scope_filters.items():
        if extra.get(key) == value:
            matched += 1
        elif key == "user_id" and candidate.item.scope == MemoryScope.USER:
            # 用户级记忆必须显式匹配 user_id，不能因为 scope=user 就给跨用户加分。
            matched += 0

    return matched / total if total > 0 else 0.5


# ---------------------------------------------------------------------------
# Reranker
# ---------------------------------------------------------------------------

class Reranker:
    """跨域统一重排器。

    Parameters
    ----------
    llm_client:
        LLMClient 实例。传 None 则只使用多因子打分。
    factor_weights:
        各因子的权重。传 None 使用默认值。
    use_llm_rerank:
        是否启用 LLM 语义重排（需 llm_client 非 None）。
    """

    def __init__(
        self,
        llm_client: "LLMClient | None" = None,
        *,
        factor_weights: dict[str, float] | None = None,
        use_llm_rerank: bool = False,
    ) -> None:
        """初始化重排器，输入可选 LLMClient、因子权重和是否启用 LLM 重排。"""
        self._llm = llm_client
        self._weights = factor_weights or dict(DEFAULT_FACTOR_WEIGHTS)
        self._use_llm_rerank = use_llm_rerank and llm_client is not None

    async def rerank(
        self,
        candidates: list[FusedCandidate],
        query: RewrittenQuery,
        *,
        top_k: int = 10,
    ) -> list[RankedMemory]:
        """对融合后的候选列表进行重排，返回 top_k 结果。"""
        if not candidates:
            logger.info(
                "action=rerank_empty top_k=%s",
                top_k,
            )
            return []

        logger.info(
            "action=rerank_start candidate_count=%s top_k=%s use_llm_rerank=%s",
            len(candidates),
            top_k,
            self._use_llm_rerank,
        )
        scored = self._multi_factor_score(candidates, query)

        if self._use_llm_rerank and self._llm is not None:
            try:
                scored.sort(key=lambda r: r.final_score, reverse=True)
                scored = await self._llm_rerank(scored, query)
            except Exception:
                logger.warning(
                    "LLM reranking failed, using multi-factor scores only",
                    exc_info=True,
                )

        scored.sort(key=lambda r: r.final_score, reverse=True)
        result = scored[:top_k]
        for idx, rm in enumerate(result):
            rm.rank = idx + 1
        logger.info(
            "action=rerank_done result_count=%s top_memory_ids=%s",
            len(result),
            [memory.item.memory_id for memory in result],
        )
        return result

    # ------------------------------------------------------------------
    # 多因子打分
    # ------------------------------------------------------------------

    def _multi_factor_score(
        self,
        candidates: list[FusedCandidate],
        query: RewrittenQuery,
    ) -> list[RankedMemory]:
        results: list[RankedMemory] = []

        for candidate in candidates:
            weights = self._get_effective_weights(candidate.source_domain)

            breakdown: dict[str, float] = {
                "fusion": _score_fusion(candidate),
                "importance": _score_importance(candidate),
                "confidence": _score_confidence(candidate),
                "freshness": _score_freshness(candidate),
                "topic_overlap": _score_topic_overlap(candidate, query),
                "scope_match": _score_scope_match(candidate, query),
            }

            final = sum(
                breakdown[k] * weights.get(k, 0)
                for k in breakdown
            )

            results.append(RankedMemory(
                item=candidate.item,
                final_score=final,
                score_breakdown=breakdown,
            ))

        return results

    def _get_effective_weights(
        self,
        domain: MemoryDomain,
    ) -> dict[str, float]:
        """合并默认权重与域级覆盖。"""
        overrides = _DOMAIN_WEIGHT_OVERRIDES.get(domain, {})
        if not overrides:
            return self._normalize_weights(dict(self._weights))
        merged = dict(self._weights)
        merged.update(overrides)
        return self._normalize_weights(merged)

    @staticmethod
    def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
        total = sum(v for v in weights.values() if v > 0)
        if total <= 0:
            return weights
        return {k: (v / total if v > 0 else 0.0) for k, v in weights.items()}

    # ------------------------------------------------------------------
    # LLM 语义重排
    # ------------------------------------------------------------------

    async def _llm_rerank(
        self,
        scored: list[RankedMemory],
        query: RewrittenQuery,
    ) -> list[RankedMemory]:
        """用 LLM 对 top 候选做 listwise 语义排序。

        LLM 返回的排名顺序被转化为一个 bonus 分数叠加到多因子分数上，
        而不是完全替代多因子打分结果。
        """
        window = scored[:_LLM_RERANK_WINDOW]
        if len(window) <= 1:
            return scored

        user_prompt = self._build_rerank_prompt(window, query)
        raw: dict[str, Any] = await self._llm.ajson(
            _RERANK_SYSTEM_PROMPT,
            user_prompt,
            schema=_RERANK_JSON_SCHEMA,
            temperature=0,
        )

        ranked_ids: list[str] = raw.get("ranked_ids", [])
        if not ranked_ids:
            return scored

        id_to_llm_rank: dict[str, int] = {
            mid: idx for idx, mid in enumerate(ranked_ids)
        }

        llm_bonus_weight = 0.15
        for rm in window:
            llm_rank = id_to_llm_rank.get(rm.item.memory_id)
            if llm_rank is not None:
                bonus = 1.0 / (llm_rank + 1)
                rm.score_breakdown["llm_rerank"] = bonus
                rm.final_score += bonus * llm_bonus_weight

        return scored

    @staticmethod
    def _build_rerank_prompt(
        candidates: list[RankedMemory],
        query: RewrittenQuery,
    ) -> str:
        parts = [f"User query: {query.rewritten_text or query.original.query_text}\n"]
        parts.append("Memory candidates:")
        for rm in candidates:
            text = rm.item.summary_text or rm.item.content_text
            if len(text) > 200:
                text = text[:200] + "..."
            parts.append(
                f"- ID: {rm.item.memory_id} | "
                f"Domain: {rm.item.domain.value} | "
                f"Content: {text}"
            )
        return "\n".join(parts)
