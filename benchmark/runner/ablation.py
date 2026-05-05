"""Ablation experiment framework.

Runs the same benchmark multiple times with different components disabled
to measure each component's contribution to overall performance.

Usage:
    from benchmark.runner.ablation import run_ablation
    results = run_ablation(config)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .runner import BenchmarkRunner
from .types import AblationVariant, BenchmarkRunResult, RunnerConfig

logger = logging.getLogger(__name__)

ABLATION_VARIANTS: list[dict] = [
    {
        "name": "full_pipeline",
        "description": "完整链路：LLM分类 + 规则抽取 + 准入过滤 + 去重合并",
    },
    {
        "name": "no_dedup",
        "description": "去掉去重合并，每次抽取都视为新记忆",
        "disabled": ["dedup"],
    },
    {
        "name": "no_admission",
        "description": "去掉准入过滤，所有事件都落记忆",
        "disabled": ["admission"],
    },
    {
        "name": "no_supersede",
        "description": "去掉淘汰管理，旧记忆不会自动过期",
        "disabled": ["supersede"],
    },
]


@dataclass
class AblationReport:
    run_id: str
    variants: list[AblationVariant] = field(default_factory=list)

    @property
    def baseline_score(self) -> float:
        if self.variants and self.variants[0].result:
            return self.variants[0].result.overall_score
        return 0.0

    def contribution(self, variant_name: str) -> float:
        """Return the contribution of a component: baseline - variant_score."""
        baseline = self.baseline_score
        for v in self.variants:
            if v.name == variant_name and v.result:
                return round(baseline - v.result.overall_score, 1)
        return 0.0

    def summary(self) -> str:
        lines = ["# Ablation Study Report", ""]
        lines.append(f"Baseline (full pipeline): {self.baseline_score:.1f} 分")
        lines.append("")
        lines.append("| 移除组件 | 得分 | 贡献 (Δ分数) | 说明 |")
        lines.append("|---------|------|-------------|------|")
        for v in self.variants[1:]:  # skip full_pipeline
            if v.result:
                delta = self.contribution(v.name)
                lines.append(f"| {v.name} | {v.result.overall_score:.1f} | {delta:+.1f} | {v.description} |")
        lines.append("")
        lines.append("> 贡献 = 完整链路得分 - 去掉组件后得分。正值表示该组件对整体性能有正向贡献。")
        return "\n".join(lines)


def run_ablation(base_config: RunnerConfig) -> AblationReport:
    """Run ablation experiments comparing full pipeline against variants."""
    import time
    run_id = base_config.run_id
    report = AblationReport(run_id=run_id)

    for i, variant_def in enumerate(ABLATION_VARIANTS):
        logger.info("Ablation [%d/%d]: %s", i + 1, len(ABLATION_VARIANTS), variant_def["name"])

        variant_config = RunnerConfig(
            run_id=f"{run_id}-{variant_def['name']}",
            suite_name=base_config.suite_name,
            case_ids=list(base_config.case_ids),
            datasets_dir=base_config.datasets_dir,
            keep_temp=False,
            ablation=True,
        )

        try:
            runner = BenchmarkRunner(variant_config)
            result = runner.run()
        except Exception as exc:
            logger.exception("Ablation variant '%s' failed", variant_def["name"])
            result = None

        report.variants.append(AblationVariant(
            name=variant_def["name"],
            description=variant_def.get("description", ""),
            disabled_components=variant_def.get("disabled", []),
            result=result,
        ))

    return report
