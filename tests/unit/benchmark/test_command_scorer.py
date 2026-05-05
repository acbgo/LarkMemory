from __future__ import annotations

from benchmark.runner.scorer import score_case
from benchmark.runner.types import BenchmarkCase
from src.retrieval import MemoryDomain, MemoryItem, RankedMemory


def test_command_exact_match_uses_cli_workflow_command_output() -> None:
    """CLI 命令评分应比较可还原命令，而不是 MemoryCore 的多行展示文本。"""
    case = BenchmarkCase(
        case_id="cmd_ret_999",
        category="command_memory",
        test_type="retrieval_recall",
        scenario="命令模板召回后还原为期望命令",
        difficulty="easy",
        time_span_days=1,
        input_events=[],
        query="项目部署命令",
        expected={
            "suggested_command": "python scripts/deploy.py --env staging --region us-east-1",
            "evidence_event_ids": ["e1"],
            "answer_keywords": ["deploy.py", "staging", "us-east-1"],
        },
        metrics=["top1_hit", "command_exact_match"],
    )
    item = MemoryItem(
        memory_id="mem_1",
        domain=MemoryDomain.CLI_WORKFLOW,
        memory_type="cli_workflow",
        content_text=(
            "命令模板: python scripts/deploy.py --env {env} --region {region}\n"
            "命令: python scripts/deploy.py\n"
            "参数绑定:\n"
            "  --env staging (1次)\n"
            "  --region us-east-1 (1次)"
        ),
        extra={
            "source_event_id": "e1",
            "workflow": {
                "command_template": "python scripts/deploy.py --env {env} --region {region}",
                "parameter_bindings": [
                    {"param_name": "env", "param_value": "staging"},
                    {"param_name": "region", "param_value": "us-east-1"},
                ],
            },
        },
    )

    result = score_case(case, [RankedMemory(item=item, final_score=1.0, rank=1)])

    metrics = {metric.metric_id: metric for metric in result.metric_results}
    assert metrics["top1_hit"].passed
    assert metrics["command_exact_match"].passed


def test_command_exact_match_accepts_equivalent_script_path() -> None:
    """脚本命令可用绝对路径存储，但 benchmark 期望常用相对路径表达。"""
    case = BenchmarkCase(
        case_id="cmd_ret_998",
        category="command_memory",
        test_type="retrieval_recall",
        scenario="脚本绝对路径与相对路径等价",
        difficulty="easy",
        time_span_days=1,
        input_events=[],
        query="py 前缀补全",
        expected={
            "suggested_command": "python scripts/train.py --epochs 3",
            "evidence_event_ids": ["e1"],
            "answer_keywords": ["python", "train.py"],
        },
        metrics=["command_exact_match"],
    )
    item = MemoryItem(
        memory_id="mem_2",
        domain=MemoryDomain.CLI_WORKFLOW,
        memory_type="cli_workflow",
        content_text="命令模板: python C:\\repo\\scripts\\train.py --epochs {epochs}",
        extra={
            "source_event_id": "e1",
            "workflow": {
                "command_template": "python C:\\repo\\scripts\\train.py --epochs {epochs}",
                "parameter_bindings": [
                    {"param_name": "epochs", "param_value": "3"},
                ],
            },
        },
    )

    result = score_case(case, [RankedMemory(item=item, final_score=1.0, rank=1)])

    metrics = {metric.metric_id: metric for metric in result.metric_results}
    assert metrics["command_exact_match"].passed
