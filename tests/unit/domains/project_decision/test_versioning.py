from __future__ import annotations

from dataclasses import asdict
import shutil
import uuid
from pathlib import Path

from src.domains.project_decision import ProjectDecision, ProjectDecisionVersionManager
from src.storage import MemoryCoreStore


def _store() -> MemoryCoreStore:
    root = Path.cwd() / ".tmp-tests"
    root.mkdir(exist_ok=True)
    temp_dir = root / f"project-decision-versioning-{uuid.uuid4().hex}"
    temp_dir.mkdir()
    store = MemoryCoreStore(str(temp_dir / "memory.db"))
    store.create_table()
    store._test_temp_dir = temp_dir  # type: ignore[attr-defined]
    return store


def _cleanup(store: MemoryCoreStore) -> None:
    shutil.rmtree(store._test_temp_dir, ignore_errors=True)  # type: ignore[attr-defined]


def _decision(
    memory_id: str,
    *,
    project_id: str = "project-1",
    topic: str = "截止日期",
    decision_text: str = "确认截止日期是 5 号",
) -> ProjectDecision:
    return ProjectDecision(
        decision_id=memory_id,
        project_id=project_id,
        topic=topic,
        decision=decision_text,
        stage="上线前",
        source_ref=f"source-{memory_id}",
        decided_at="2026-04-26T00:00:00Z",
        confidence=0.9,
        importance=0.8,
    )


def test_detect_update_supersedes_same_project_topic_changed_decision() -> None:
    old = _decision("mem-old", decision_text="确认截止日期是 5 号")
    new = _decision("mem-new", decision_text="改为 8 号交付")

    decision = ProjectDecisionVersionManager(_store()).detect_update(
        new,
        [asdict(old.to_memory_core())],
    )

    assert decision.should_supersede
    assert decision.old_memory_id == "mem-old"
    assert decision.new_memory_id == "mem-new"


def test_detect_update_does_not_supersede_reason_only_addition() -> None:
    old = _decision("mem-old", decision_text="确认截止日期是 5 号")
    new = _decision("mem-new", decision_text="确认截止日期是 5 号")

    decision = ProjectDecisionVersionManager(_store()).detect_update(
        new,
        [asdict(old.to_memory_core())],
    )

    assert not decision.should_supersede


def test_detect_update_ignores_different_project() -> None:
    old = _decision("mem-old", project_id="project-1")
    new = _decision("mem-new", project_id="project-2", decision_text="改为 8 号交付")

    decision = ProjectDecisionVersionManager(_store()).detect_update(
        new,
        [asdict(old.to_memory_core())],
    )

    assert not decision.should_supersede


def test_apply_supersede_calls_store_and_version_chain_restores_decisions() -> None:
    store = _store()
    try:
        old = _decision("mem-old")
        new = _decision("mem-new", decision_text="改为 8 号交付")
        store.insert_memory_core(old.to_memory_core())
        store.insert_memory_core(new.to_memory_core())
        manager = ProjectDecisionVersionManager(store)

        manager.apply_supersede("mem-old", "mem-new")
        chain = manager.get_version_chain("mem-new")

        assert store.get_memory("mem-old")["status"] == "superseded"
        assert [decision.decision_id for decision in chain] == ["mem-old", "mem-new"]
    finally:
        _cleanup(store)
