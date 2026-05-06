from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class _FakeResult:
    run_id: str = "smoke"
    suite_name: str = "decision_memory"
    overall_score: float = 88.5
    passed_cases: int = 7
    total_cases: int = 10
    failed_cases: int = 3
    error_cases: int = 0
    rating: str = "优秀"


@dataclass(slots=True)
class _FakeCaseResult:
    case_id: str
    category: str = "decision_memory"
    test_type: str = "retrieval_recall"
    difficulty: str = "easy"
    metric_results: list[object] | None = None
    error: str | None = None


@dataclass(slots=True)
class _FakeMetric:
    metric_id: str = "recall_at_3"
    value: float = 1.0
    passed: bool = True


def test_parse_args_defaults_to_decision_memory_suite() -> None:
    from benchmark.run_project_decision_benchmark import parse_args

    args = parse_args([])

    assert args.suite == "decision_memory"
    assert args.run_id.startswith("project-decision-")
    assert args.reports_dir == Path("benchmark/reports")
    assert args.temp_dir == Path("benchmark/.tmp-runs")
    assert args.case_id == []
    assert args.keep_temp is False
    assert args.quiet is False
    assert args.verbose_logs is False


def test_parse_args_accepts_repeated_case_ids() -> None:
    from benchmark.run_project_decision_benchmark import parse_args

    args = parse_args(["--case-id", "dec_ret_001", "--case-id", "dec_contra_001"])

    assert args.case_id == ["dec_ret_001", "dec_contra_001"]


def test_main_runs_benchmark_and_saves_report(monkeypatch, capsys) -> None:
    from benchmark import run_project_decision_benchmark as cli

    calls: dict[str, object] = {}

    class FakeRunner:
        def __init__(self, config) -> None:
            calls["config"] = config

        def run(self) -> _FakeResult:
            calls["ran"] = True
            return _FakeResult()

    def fake_save_report(result: _FakeResult, path: str) -> None:
        calls["saved_result"] = result
        calls["saved_path"] = path

    monkeypatch.setattr(cli, "BenchmarkRunner", FakeRunner)
    monkeypatch.setattr(cli, "save_report", fake_save_report)

    exit_code = cli.main(
        [
            "--run-id",
            "smoke",
            "--case-id",
            "dec_ret_001",
            "--reports-dir",
            "benchmark/.tmp-report",
            "--temp-dir",
            "benchmark/.tmp-runs",
            "--keep-temp",
        ]
    )

    config = calls["config"]
    assert exit_code == 0
    assert calls["ran"] is True
    assert config.run_id == "smoke"
    assert config.suite_name == "decision_memory"
    assert config.case_ids == ["dec_ret_001"]
    assert config.keep_temp is True
    assert Path(config.temp_root) == Path("benchmark/.tmp-runs")
    assert Path(calls["saved_path"]) == Path("benchmark/.tmp-report")
    output = capsys.readouterr().out
    assert "overall=88.5" in output
    assert "passed=7/10" in output


def test_main_prints_case_progress(monkeypatch, capsys) -> None:
    from benchmark import run_project_decision_benchmark as cli

    class FakeRunner:
        def __init__(self, config) -> None:
            self.config = config

        def run(self) -> _FakeResult:
            self.config.progress_callback("case_start", 1, 2, "dec_ret_001", None)
            self.config.progress_callback(
                "case_done",
                1,
                2,
                "dec_ret_001",
                _FakeCaseResult("dec_ret_001", metric_results=[_FakeMetric()]),
            )
            self.config.progress_callback("case_start", 2, 2, "dec_contra_001", None)
            self.config.progress_callback(
                "case_done",
                2,
                2,
                "dec_contra_001",
                _FakeCaseResult("dec_contra_001", error="boom"),
            )
            return _FakeResult()

    monkeypatch.setattr(cli, "BenchmarkRunner", FakeRunner)
    monkeypatch.setattr(cli, "save_report", lambda result, path: None)

    cli.main(["--run-id", "progress-smoke"])

    output = capsys.readouterr().out
    assert "benchmark start run_id=progress-smoke suite=decision_memory" in output
    assert "[1/2] start dec_ret_001" in output
    assert "[1/2] done dec_ret_001 status=passed" in output
    assert "[2/2] done dec_contra_001 status=error" in output


def test_quiet_suppresses_case_progress(monkeypatch, capsys) -> None:
    from benchmark import run_project_decision_benchmark as cli

    class FakeRunner:
        def __init__(self, config) -> None:
            self.config = config

        def run(self) -> _FakeResult:
            assert self.config.progress_callback is None
            return _FakeResult()

    monkeypatch.setattr(cli, "BenchmarkRunner", FakeRunner)
    monkeypatch.setattr(cli, "save_report", lambda result, path: None)

    cli.main(["--run-id", "quiet-smoke", "--quiet"])

    output = capsys.readouterr().out
    assert "benchmark start" not in output
    assert "[1/2]" not in output
    assert "benchmark done" in output


def test_main_reports_runner_startup_failure(monkeypatch, capsys) -> None:
    from benchmark import run_project_decision_benchmark as cli

    class RaisingRunner:
        def __init__(self, config) -> None:
            self.config = config

        def run(self) -> _FakeResult:
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(cli, "BenchmarkRunner", RaisingRunner)

    exit_code = cli.main(["--run-id", "fail-smoke"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "benchmark failed run_id=fail-smoke" in captured.err
    assert "database unavailable" in captured.err


def test_script_help_runs_when_executed_by_path() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "benchmark/run_project_decision_benchmark.py",
            "--help",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "ProjectDecision benchmark" in result.stdout
