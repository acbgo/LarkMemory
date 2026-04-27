from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from src.domains.project_decision import ProjectDecision, ProjectDecisionQuery, ProjectDecisionRetriever
from src.storage import MemoryCoreStore


def _store() -> MemoryCoreStore:
    root = Path.cwd() / ".tmp-tests"
    root.mkdir(exist_ok=True)
    temp_dir = root / f"project-decision-retriever-{uuid.uuid4().hex}"
    temp_dir.mkdir()
    store = MemoryCoreStore(str(temp_dir / "memory.db"))
    store.create_table()
    store._test_temp_dir = temp_dir  # type: ignore[attr-defined]
    return store


def _cleanup(store: MemoryCoreStore) -> None:
    shutil.rmtree(store._test_temp_dir, ignore_errors=True)  # type: ignore[attr-defined]


def _insert(
    store: MemoryCoreStore,
    memory_id: str,
    *,
    project_id: str = "project-1",
    topic: str = "检索层方案",
    stage: str = "技术选型",
    status: str = "confirmed",
) -> None:
    decision = ProjectDecision(
        decision_id=memory_id,
        project_id=project_id,
        topic=topic,
        decision="采用方案 B",
        stage=stage,
        status=status,  # type: ignore[arg-type]
        source_ref=f"source-{memory_id}",
        confidence=0.9,
        importance=0.8,
    )
    store.insert_memory_core(decision.to_memory_core())
    if status == "superseded":
        store.update_memory_status(memory_id, "superseded")


def test_retrieve_filters_by_project_id() -> None:
    store = _store()
    try:
        _insert(store, "mem-project-1", project_id="project-1")
        _insert(store, "mem-project-2", project_id="project-2")

        results = ProjectDecisionRetriever(store).retrieve(
            ProjectDecisionQuery(query_text="检索层方案", project_id="project-1")
        )

        assert [result.decision.decision_id for result in results] == ["mem-project-1"]
    finally:
        _cleanup(store)


def test_retrieve_matches_topic_and_stage() -> None:
    store = _store()
    try:
        _insert(store, "mem-target", topic="数据库选型", stage="技术选型")
        _insert(store, "mem-other", topic="上线计划", stage="联调")

        results = ProjectDecisionRetriever(store).retrieve(
            ProjectDecisionQuery(query_text="数据库", topic="数据库选型", stage="技术选型")
        )

        assert len(results) == 1
        assert results[0].decision.decision_id == "mem-target"
        assert "topic" in results[0].matched_fields
        assert "stage" in results[0].matched_fields
    finally:
        _cleanup(store)


def test_retrieve_excludes_superseded_by_default() -> None:
    store = _store()
    try:
        _insert(store, "mem-active")
        _insert(store, "mem-old", status="superseded")

        results = ProjectDecisionRetriever(store).retrieve(
            ProjectDecisionQuery(query_text="检索层方案", include_superseded=False)
        )

        assert {result.decision.decision_id for result in results} == {"mem-active"}
    finally:
        _cleanup(store)


def test_retrieve_cards_applies_min_score() -> None:
    store = _store()
    try:
        _insert(store, "mem-card")

        cards = ProjectDecisionRetriever(store).retrieve_cards(
            ProjectDecisionQuery(query_text="为什么选方案 B", topic="检索层方案", project_id="project-1"),
            min_score=0.55,
        )

        assert len(cards) == 1
        assert cards[0]["type"] == "project_decision_card"
        assert cards[0]["score"] >= 0.55
        assert cards[0]["match_reason"]
    finally:
        _cleanup(store)

