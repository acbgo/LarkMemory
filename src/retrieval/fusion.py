"""融合多个领域的召回结果。

使用 Reciprocal Rank Fusion (RRF) 加域权重对多域召回结果进行
归一化融合和去重，输出统一的候选列表。
"""

from __future__ import annotations

from ._types import (
    DomainRecallResult,
    FusedCandidate,
    IntentResult,
    MemoryDomain,
)

# ---------------------------------------------------------------------------
# 默认配置
# ---------------------------------------------------------------------------

DEFAULT_RRF_K = 60
DEFAULT_PRIMARY_WEIGHT = 1.0
DEFAULT_SECONDARY_WEIGHT = 0.5
DEFAULT_UNRELATED_WEIGHT = 0.2


# ---------------------------------------------------------------------------
# ResultFusion
# ---------------------------------------------------------------------------

class ResultFusion:
    """跨域结果融合器。

    Parameters
    ----------
    rrf_k:
        RRF 公式中的常数 k，控制排名靠后结果的衰减速度。
    primary_weight:
        主查域的权重。
    secondary_weight:
        辅查域的权重。
    unrelated_weight:
        既不是主查也不是辅查的域的权重（通常不应出现，作为兜底）。
    """

    def __init__(
        self,
        *,
        rrf_k: int = DEFAULT_RRF_K,
        primary_weight: float = DEFAULT_PRIMARY_WEIGHT,
        secondary_weight: float = DEFAULT_SECONDARY_WEIGHT,
        unrelated_weight: float = DEFAULT_UNRELATED_WEIGHT,
    ) -> None:
        self._rrf_k = rrf_k
        self._primary_weight = primary_weight
        self._secondary_weight = secondary_weight
        self._unrelated_weight = unrelated_weight

    def fuse(
        self,
        recalls: list[DomainRecallResult],
        intent: IntentResult,
    ) -> list[FusedCandidate]:
        """融合多域召回结果，返回按 fusion_score 降序排列的候选列表。

        Parameters
        ----------
        recalls:
            各域 retriever 返回的召回结果列表。
        intent:
            意图分析结果，用于确定各域的权重。

        Returns
        -------
        按 fusion_score 降序排列的 FusedCandidate 列表。
        """
        primary_set = set(intent.primary_domains)
        secondary_set = set(intent.secondary_domains)

        # memory_id -> 累加候选。RRF 的价值在于多路召回会共同增强同一记忆。
        best: dict[str, FusedCandidate] = {}
        best_single_score: dict[str, float] = {}

        for recall in recalls:
            domain_weight = self._get_domain_weight(
                recall.domain, primary_set, secondary_set,
            )

            for rank_idx, item in enumerate(recall.items):
                rrf_score = self._rrf_score(rank_idx)
                fusion_score = rrf_score * domain_weight

                candidate = FusedCandidate(
                    item=item,
                    source_domain=recall.domain,
                    domain_rank=rank_idx + 1,
                    fusion_score=fusion_score,
                )

                existing = best.get(item.memory_id)
                if existing is None:
                    best[item.memory_id] = candidate
                    best_single_score[item.memory_id] = fusion_score
                else:
                    existing.fusion_score += fusion_score
                    if fusion_score > best_single_score[item.memory_id]:
                        existing.source_domain = recall.domain
                        existing.domain_rank = rank_idx + 1
                        best_single_score[item.memory_id] = fusion_score

        result = sorted(best.values(), key=lambda c: c.fusion_score, reverse=True)
        return result

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _rrf_score(self, rank: int) -> float:
        """Reciprocal Rank Fusion: 1 / (k + rank)，rank 从 0 开始。"""
        return 1.0 / (self._rrf_k + rank + 1)

    def _get_domain_weight(
        self,
        domain: MemoryDomain,
        primary_set: set[MemoryDomain],
        secondary_set: set[MemoryDomain],
    ) -> float:
        if domain in primary_set:
            return self._primary_weight
        if domain in secondary_set:
            return self._secondary_weight
        return self._unrelated_weight
