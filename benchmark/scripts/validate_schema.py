#!/usr/bin/env python3
"""Validate all benchmark JSONL files against schema.json, with extra semantic checks."""

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Valid test_type per category
VALID_TEST_TYPES = {
    "command_memory": {"retrieval_recall", "anti_interference", "efficiency", "cross_project"},
    "decision_memory": {"retrieval_recall", "anti_interference", "contradiction_update", "efficiency", "long_term_retention", "abstention", "cross_project"},
    "preference_memory": {"retrieval_recall", "anti_interference", "contradiction_update", "efficiency", "abstention", "cross_project"},
    "knowledge_health": {"retrieval_recall", "anti_interference", "contradiction_update", "long_term_retention", "abstention"},
}

# Difficulty -> time_span_days ranges
DIFFICULTY_RANGES = {
    "easy": (0, 7),
    "medium": (8, 90),
    "hard": (91, 9999),
}

TOP_LEVEL_REQUIRED = {"case_id", "category", "test_type", "scenario", "difficulty", "input_events", "query", "expected", "metrics"}
TOP_LEVEL_ALLOWED = TOP_LEVEL_REQUIRED | {"time_span_days"}
EVENT_REQUIRED = {"event_id", "timestamp", "source", "content"}
EVENT_ALLOWED = EVENT_REQUIRED | {"speaker", "context"}


def validate_case_shape(case, schema):
    """Validate required fields, enum values, and unexpected fields without third-party deps."""
    missing = TOP_LEVEL_REQUIRED - case.keys()
    if missing:
        raise ValueError(f"missing required field(s): {sorted(missing)}")

    extra = set(case.keys()) - TOP_LEVEL_ALLOWED
    if extra:
        raise ValueError(f"unexpected top-level field(s): {sorted(extra)}")

    properties = schema["properties"]
    for field in ("category", "test_type", "difficulty"):
        allowed = set(properties[field]["enum"])
        if case[field] not in allowed:
            raise ValueError(f"{field} '{case[field]}' not in {sorted(allowed)}")

    if not isinstance(case["input_events"], list) or not case["input_events"]:
        raise ValueError("input_events must be a non-empty list")

    for event in case["input_events"]:
        missing_event = EVENT_REQUIRED - event.keys()
        if missing_event:
            raise ValueError(f"event missing required field(s): {sorted(missing_event)}")
        extra_event = set(event.keys()) - EVENT_ALLOWED
        if extra_event:
            raise ValueError(f"event has unexpected field(s): {sorted(extra_event)}")

    expected = case["expected"]
    expected_allowed = set(properties["expected"]["properties"].keys())
    extra_expected = set(expected.keys()) - expected_allowed
    if extra_expected:
        raise ValueError(f"expected has unexpected field(s): {sorted(extra_expected)}")

    metric_allowed = set(properties["metrics"]["items"]["enum"])
    bad_metrics = [metric for metric in case["metrics"] if metric not in metric_allowed]
    if bad_metrics:
        raise ValueError(f"metrics contain unknown value(s): {bad_metrics}")


def main():
    """Validate benchmark JSONL cases against schema and semantic constraints."""
    schema_path = BASE_DIR / "schema.json"
    datasets_dir = BASE_DIR / "datasets"

    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)

    total = 0
    passed = 0
    failed = 0
    warnings = []

    jsonl_files = sorted(datasets_dir.glob("*.jsonl"))
    if not jsonl_files:
        print("ERROR: No JSONL files found in datasets/")
        sys.exit(1)

    for jsonl_file in jsonl_files:
        cases = []
        with open(jsonl_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    cases.append(json.loads(line))

        file_ok = 0
        for i, case in enumerate(cases):
            total += 1
            cid = case.get("case_id", f"?")
            try:
                validate_case_shape(case, schema)

                # Semantic checks
                cat = case["category"]
                tt = case["test_type"]
                diff = case["difficulty"]
                tsd = case["time_span_days"]
                evts = case["input_events"]
                expected = case["expected"]

                # Check test_type is valid for category
                if tt not in VALID_TEST_TYPES.get(cat, set()):
                    raise ValueError(f"test_type '{tt}' not valid for category '{cat}'")

                # Check difficulty matches time_span_days
                lo, hi = DIFFICULTY_RANGES[diff]
                if tsd < lo or tsd > hi:
                    raise ValueError(f"time_span_days={tsd} does not match difficulty '{diff}' ({lo}-{hi})")

                # Check evidence_event_ids refer to valid events
                evid_ids = expected.get("evidence_event_ids", [])
                valid_ids = {e["event_id"] for e in evts}
                for eid in evid_ids:
                    if eid not in valid_ids:
                        raise ValueError(f"evidence_event_id '{eid}' not found in input_events")

                # Check superseded_event_ids
                sup_ids = expected.get("superseded_event_ids", [])
                for sid in sup_ids:
                    if sid not in valid_ids:
                        raise ValueError(f"superseded_event_id '{sid}' not found in input_events")

                # Abstention tests: should_retrieve should be false
                if tt == "abstention" and expected.get("should_retrieve", True):
                    raise ValueError("abstention test must have should_retrieve=false")

                # Abstention tests: should have abstention_keywords
                if tt == "abstention" and not expected.get("abstention_keywords"):
                    warnings.append(f"[{cid}] abstention test missing abstention_keywords (recommended)")

                # Non-abstention tests: should have answer_keywords
                if tt != "abstention" and not expected.get("answer_keywords"):
                    raise ValueError(f"non-abstention test must have answer_keywords")

                # Cross-project tests: should have events from multiple projects
                if tt == "cross_project":
                    projects = set()
                    for e in evts:
                        p = (e.get("context") or {}).get("project", "")
                        if p:
                            projects.add(p)
                    if len(projects) < 2:
                        warnings.append(f"[{cid}] cross_project test has only {len(projects)} project(s), expected ≥2")

                # Noise count checks
                noise_count = sum(1 for e in evts if e["event_id"].startswith("noise_"))
                signal_count = len(evts) - noise_count
                if diff == "hard" and noise_count < 20:
                    warnings.append(f"[{cid}] hard difficulty with only {noise_count} noise events (recommended >=30)")

                # Contradiction update: should have current_value
                if tt == "contradiction_update" and not expected.get("current_value"):
                    warnings.append(f"[{cid}] contradiction_update missing current_value")

                passed += 1
                file_ok += 1
            except jsonschema.ValidationError as e:
                failed += 1
                print(f"  FAIL [{jsonl_file.name}] case {i} ({cid}): {e.message}")
            except ValueError as e:
                failed += 1
                print(f"  FAIL [{jsonl_file.name}] case {i} ({cid}): {e}")

        status = "OK" if file_ok == len(cases) else "FAIL"
        print(f"{status} {jsonl_file.name}: {file_ok}/{len(cases)} passed")

    if warnings:
        print(f"\nWARN {len(warnings)} warning(s):")
        for w in warnings:
            print(f"  WARN: {w}")

    print(f"\nTotal: {passed}/{total} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)

if __name__ == "__main__":
    main()
