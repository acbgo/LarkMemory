from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from benchmark.eval_project_decision import ProjectDecisionBenchmark, load_jsonl, parse_args


def _tmp_dir() -> Path:
    root = Path.cwd() / ".tmp-tests"
    root.mkdir(exist_ok=True)
    path = root / f"benchmark-{uuid.uuid4().hex}"
    path.mkdir()
    return path


def test_load_jsonl_reads_utf8_objects() -> None:
    temp_dir = _tmp_dir()
    try:
        dataset = temp_dir / "cases.jsonl"
        dataset.write_text(
            '{"case_id":"c1","query":"SQLite 选型"}\n{"case_id":"c2","query":"支付回滚"}\n',
            encoding="utf-8",
        )

        records = load_jsonl(dataset)

        assert [record["case_id"] for record in records] == ["c1", "c2"]
        assert records[0]["query"] == "SQLite 选型"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_write_reports_creates_json_and_markdown() -> None:
    temp_dir = _tmp_dir()
    try:
        runner = ProjectDecisionBenchmark(
            base_url="http://127.0.0.1:8765",
            sqlite_path=str(temp_dir / "missing.db"),
            dataset_dir=temp_dir,
            results_dir=temp_dir / "results",
            project_id="project-1",
            workspace_id="workspace-1",
            team_id="team-1",
            chat_id="",
            timeout=1,
            ingest_wait=0,
            top_k=3,
        )
        report = {
            "run_id": runner.run_id,
            "health": {"status": "ok"},
            "project_id": "project-1",
            "seed_count": 1,
            "query_count": 1,
            "ingest": {"store_recall": 1.0},
            "retrieval": {
                "summary": {"hit_at_k": 1.0, "mrr": 1.0, "false_positive_rate": 0.0},
                "cases": [
                    {
                        "case_id": "q1",
                        "query": "SQLite 选型",
                        "score": {"hit_at_k": 1.0, "mrr": 1.0, "false_positive": 0.0},
                        "top_results": [],
                    }
                ],
            },
            "proactive": {"record_count": 0, "status_counts": {}},
            "official_requirements": {
                "anti_interference": {
                    "noise_count": 30,
                    "summary": {"hit_at_k": 1.0, "mrr": 1.0, "false_positive_rate": 0.0},
                    "cases": [],
                },
                "contradiction_update": {
                    "update_event_count": 2,
                    "summary": {"hit_at_k": 1.0, "mrr": 1.0, "false_positive_rate": 0.0},
                    "cases": [],
                },
                "efficiency": {
                    "summary": {
                        "case_count": 1,
                        "avg_char_saving_rate": 0.8,
                        "avg_step_saving_rate": 0.5,
                    },
                    "cases": [],
                },
            },
        }

        runner._write_reports(report)

        json_path = runner.results_dir / f"{runner.run_id}.json"
        md_path = runner.results_dir / f"{runner.run_id}.md"
        assert json.loads(json_path.read_text(encoding="utf-8"))["run_id"] == runner.run_id
        markdown = md_path.read_text(encoding="utf-8")
        assert "Retrieval hit@3" in markdown
        assert "Official Requirement Coverage" in markdown
        assert "Anti-interference hit@3" in markdown
        assert "Contradiction update hit@3" in markdown
        assert "Efficiency char saving" in markdown
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_progress_output_is_disabled_when_quiet() -> None:
    temp_dir = _tmp_dir()
    try:
        runner = ProjectDecisionBenchmark(
            base_url="http://127.0.0.1:8765",
            sqlite_path=str(temp_dir / "missing.db"),
            dataset_dir=temp_dir,
            results_dir=temp_dir / "results",
            project_id="project-1",
            workspace_id="workspace-1",
            team_id="team-1",
            chat_id="",
            timeout=1,
            ingest_wait=0,
            top_k=3,
            verbose=False,
        )

        assert runner.verbose is False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_parse_args_supports_quiet_flag() -> None:
    args = parse_args(["--quiet"])

    assert args.quiet is True


def test_summarize_ingest_counts_noise_storage() -> None:
    temp_dir = _tmp_dir()
    try:
        runner = ProjectDecisionBenchmark(
            base_url="http://127.0.0.1:8765",
            sqlite_path=str(temp_dir / "missing.db"),
            dataset_dir=temp_dir,
            results_dir=temp_dir / "results",
            project_id="project-1",
            workspace_id="workspace-1",
            team_id="team-1",
            chat_id="",
            timeout=1,
            ingest_wait=0,
            top_k=3,
            verbose=False,
        )
        seeds = [
            {"case_id": "seed-1", "scenario": "技术选型", "expected": {"should_store": True}},
        ]
        ingest_results = [
            {"case_id": "seed-1", "response": {"memory_ids": ["mem-1"]}, "status": "ok", "event_id": "e1"},
            {"case_id": "noise-1", "response": {"memory_ids": ["mem-noise"]}, "status": "ok", "event_id": "e2"},
            {"case_id": "noise-2", "response": {"memory_ids": []}, "status": "ok", "event_id": "e3"},
        ]

        summary = runner._summarize_ingest(ingest_results, seeds)

        assert summary["store_recall"] == 1.0
        assert summary["noise_case_count"] == 2
        assert summary["noise_store_count"] == 1
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
