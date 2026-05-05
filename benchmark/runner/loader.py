from __future__ import annotations

import json
import logging
from pathlib import Path

from .types import BenchmarkCase

logger = logging.getLogger(__name__)

# 4 competition direction datasets
DIRECTION_FILES: dict[str, str] = {
    "command_memory": "command_memory.jsonl",
    "decision_memory": "decision_memory.jsonl",
    "preference_memory": "preference_memory.jsonl",
    "knowledge_health": "knowledge_health.jsonl",
}

# 7 test types (reused for cross-file filtering)
TEST_TYPES = [
    "retrieval_recall",
    "anti_interference",
    "contradiction_update",
    "efficiency",
    "long_term_retention",
    "abstention",
    "cross_project",
]


def load_cases(
    datasets_dir: str = "benchmark/datasets",
    suite_name: str = "all",
    case_ids: list[str] | None = None,
) -> list[BenchmarkCase]:
    """Load benchmark cases from direction-based JSONL files.

    suite_name:
      - "all" — all 4 directions, all test types
      - a direction like "decision_memory" — that file only
      - a test type like "anti_interference" — across all files, filtered
    """
    base = Path(datasets_dir)
    case_id_set = set(case_ids or [])

    # Determine which files to load
    if suite_name == "all" or suite_name == "":
        files = [base / f for f in DIRECTION_FILES.values() if (base / f).exists()]
    elif suite_name in DIRECTION_FILES:
        target = base / DIRECTION_FILES[suite_name]
        files = [target] if target.exists() else []
    elif suite_name in TEST_TYPES:
        # Cross-file filter: load all direction files, filter by test_type later
        files = [base / f for f in DIRECTION_FILES.values() if (base / f).exists()]
    else:
        logger.warning("Unknown suite_name '%s', loading all", suite_name)
        files = [base / f for f in DIRECTION_FILES.values() if (base / f).exists()]

    if not files:
        logger.warning("No dataset files found in %s", datasets_dir)
        return []

    cases: list[BenchmarkCase] = []
    for filepath in files:
        direction = _direction_from_filename(filepath.name)
        with open(filepath, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                raw = json.loads(line)
                cid = raw["case_id"]

                # Filter by case_ids
                if case_id_set and cid not in case_id_set:
                    continue

                # Filter by test_type if suite_name is a test type
                if suite_name in TEST_TYPES and raw.get("test_type") != suite_name:
                    continue

                cases.append(BenchmarkCase(
                    case_id=cid,
                    category=raw["category"],
                    test_type=raw["test_type"],
                    scenario=raw.get("scenario", ""),
                    difficulty=raw.get("difficulty", "medium"),
                    time_span_days=raw.get("time_span_days", 0),
                    input_events=raw["input_events"],
                    query=raw["query"],
                    expected=raw["expected"],
                    metrics=raw.get("metrics", []),
                ))

    logger.info("Loaded %d cases (suite=%s) from %d file(s)", len(cases), suite_name, len(files))
    return cases


def _direction_from_filename(filename: str) -> str:
    for direction, fname in DIRECTION_FILES.items():
        if fname == filename:
            return direction
    return "unknown"
