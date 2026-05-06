from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark.runner.reporter import save_report
from benchmark.runner.runner import BenchmarkRunner
from benchmark.runner.types import RunnerConfig


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line options for the ProjectDecision benchmark runner."""

    default_run_id = datetime.now().strftime("project-decision-%Y%m%d-%H%M%S")
    parser = argparse.ArgumentParser(
        description="Run the LarkMemory ProjectDecision benchmark suite.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--run-id", default=default_run_id, help="Report run identifier")
    parser.add_argument(
        "--suite",
        default="decision_memory",
        help="Benchmark suite to run; defaults to the ProjectDecision dataset",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="Run one case ID; repeat this option for multiple cases",
    )
    parser.add_argument(
        "--datasets-dir",
        default="benchmark/datasets",
        help="Directory containing benchmark JSONL datasets",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("benchmark/reports"),
        help="Directory where JSON and Markdown reports are written",
    )
    parser.add_argument(
        "--temp-dir",
        type=Path,
        default=Path("benchmark/.tmp-runs"),
        help="Directory used for isolated temporary benchmark databases",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep the runner's isolated temporary DB directory after completion",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-case progress output",
    )
    parser.add_argument(
        "--verbose-logs",
        action="store_true",
        help="Show internal warning/error logs and stack traces from benchmark components",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the configured benchmark and write report artifacts."""

    args = parse_args(argv)
    _configure_logging(verbose=bool(args.verbose_logs))
    config = RunnerConfig(
        run_id=args.run_id,
        suite_name=args.suite,
        case_ids=list(args.case_id or []),
        datasets_dir=args.datasets_dir,
        temp_root=str(args.temp_dir),
        keep_temp=bool(args.keep_temp),
        progress_callback=None if args.quiet else _print_progress,
    )
    if not args.quiet:
        print(
            "benchmark start "
            f"run_id={config.run_id} "
            f"suite={config.suite_name} "
            f"case_filter={config.case_ids or 'all'} "
            f"temp_dir={args.temp_dir} "
            f"reports_dir={args.reports_dir}",
            flush=True,
        )
    try:
        result = BenchmarkRunner(config).run()
    except Exception as exc:
        print(
            f"benchmark failed run_id={config.run_id} error={type(exc).__name__}: {exc}",
            file=sys.stderr,
            flush=True,
        )
        return 1
    save_report(result, str(args.reports_dir))
    print(
        "benchmark done "
        f"run_id={result.run_id} "
        f"suite={result.suite_name} "
        f"overall={result.overall_score} "
        f"rating={result.rating} "
        f"passed={result.passed_cases}/{result.total_cases} "
        f"errors={result.error_cases} "
        f"reports_dir={args.reports_dir}"
    )
    return 0


def _configure_logging(*, verbose: bool) -> None:
    """Keep CLI progress readable unless detailed internal logs are requested."""

    logging.disable(logging.NOTSET)
    if verbose:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
        return
    logging.disable(logging.CRITICAL)


def _print_progress(
    event: str,
    index: int,
    total: int,
    case_id: str,
    case_result: object | None,
) -> None:
    """Print one-line case progress updates for long benchmark runs."""

    if event == "case_start":
        print(f"[{index}/{total}] start {case_id}", flush=True)
        return
    if event != "case_done":
        return
    error = getattr(case_result, "error", None)
    metric_results = list(getattr(case_result, "metric_results", []) or [])
    if error:
        status = "error"
    elif metric_results and all(bool(getattr(metric, "passed", False)) for metric in metric_results):
        status = "passed"
    else:
        status = "failed"
    detail = _format_metric_detail(metric_results)
    suffix = f" metrics={detail}" if detail else ""
    print(f"[{index}/{total}] done {case_id} status={status}{suffix}", flush=True)


def _format_metric_detail(metric_results: list[object]) -> str:
    """Format compact metric status for progress output."""

    parts: list[str] = []
    for metric in metric_results[:4]:
        metric_id = getattr(metric, "metric_id", "metric")
        value = getattr(metric, "value", 0.0)
        passed = bool(getattr(metric, "passed", False))
        marker = "ok" if passed else "fail"
        try:
            parts.append(f"{metric_id}={float(value):.2f}/{marker}")
        except (TypeError, ValueError):
            parts.append(f"{metric_id}={marker}")
    if len(metric_results) > 4:
        parts.append(f"+{len(metric_results) - 4}")
    return ",".join(parts)


if __name__ == "__main__":
    sys.exit(main())
