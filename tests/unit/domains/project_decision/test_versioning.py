from __future__ import annotations

from dataclasses import asdict
import shutil
import uuid
from pathlib import Path

from src.domains.project_decision import ProjectDecision, ProjectDecisionVersionManager
from src.storage import MemoryCoreStore


class FakeDecisionJudgeLLM:
    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self.payloads = list(payloads)
        self.calls: list[dict[str, object]] = []

    async def ajson(self, system_prompt: str | None, user_prompt: str, **kwargs: object) -> dict[str, object]:
        self.calls.append(
            {
                "system_prompt": system_prompt or "",
                "user_prompt": user_prompt,
                "kwargs": kwargs,
            }
        )
        if not self.payloads:
            raise AssertionError("unexpected LLM call")
        return self.payloads.pop(0)


class FailingDecisionJudgeLLM:
    async def ajson(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("judge failed")


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


def test_detect_update_marks_duplicate_when_same_project_topic_and_decision() -> None:
    old = _decision("mem-old", decision_text="确认截止日期是 5 号")
    new = _decision("mem-new", decision_text="确认截止日期是 5 号")

    decision = ProjectDecisionVersionManager(_store()).detect_update(
        new,
        [asdict(old.to_memory_core())],
    )

    assert not decision.should_supersede
    assert decision.old_memory_id == "mem-old"
    assert decision.reason == "same_scope_topic_and_same_decision"


def test_detect_update_uses_llm_duplicate_judgement_with_same_scope_topic() -> None:
    old = _decision("mem-old", decision_text="采用方案 B，而不是方案 A，因为接入成本更低")
    new = _decision("mem-new", decision_text="决定采用方案 B，而非方案 A，因为接入成本更低")
    manager = ProjectDecisionVersionManager(
        _store(),
        llm_client=FakeDecisionJudgeLLM(
            [
                {
                    "label": "duplicate",
                    "confidence": 0.96,
                    "reason": "两段结论表达的是同一个决定",
                }
            ]
        ),
    )

    decision = manager.detect_update(
        new,
        [asdict(old.to_memory_core())],
        detection_source="semantic",
    )

    assert not decision.should_supersede
    assert decision.should_reuse_existing
    assert decision.old_memory_id == "mem-old"
    assert decision.reason == "llm_duplicate"
    assert decision.detection_source == "llm"


def test_detect_update_uses_llm_supersede_judgement_with_same_scope_topic() -> None:
    old = _decision("mem-old", decision_text="采用方案 B，而不是方案 A")
    new = _decision("mem-new", decision_text="改为采用方案 C，而不是方案 B")
    manager = ProjectDecisionVersionManager(
        _store(),
        llm_client=FakeDecisionJudgeLLM(
            [
                {
                    "label": "supersede",
                    "confidence": 0.93,
                    "reason": "新结论明确替代旧结论",
                }
            ]
        ),
    )

    decision = manager.detect_update(
        new,
        [asdict(old.to_memory_core())],
        detection_source="semantic",
    )

    assert decision.should_supersede
    assert not decision.should_reuse_existing
    assert decision.old_memory_id == "mem-old"
    assert decision.reason == "llm_supersede"
    assert decision.detection_source == "llm"


def test_detect_update_treats_llm_new_as_no_match() -> None:
    old = _decision("mem-old", decision_text="采用方案 B，而不是方案 A")
    new = _decision("mem-new", decision_text="继续观察方案 D 的可行性")
    manager = ProjectDecisionVersionManager(
        _store(),
        llm_client=FakeDecisionJudgeLLM(
            [
                {
                    "label": "new",
                    "confidence": 0.91,
                    "reason": "两段结论不是重复也不是替代",
                }
            ]
        ),
    )

    decision = manager.detect_update(
        new,
        [asdict(old.to_memory_core())],
        detection_source="semantic",
    )

    assert not decision.should_supersede
    assert not decision.should_reuse_existing
    assert decision.reason == "llm_new"
    assert decision.detection_source == "llm"


def test_detect_update_falls_back_to_rules_when_llm_fails() -> None:
    old = _decision("mem-old", decision_text="确认截止日期是 5 号")
    new = _decision("mem-new", decision_text="确认截止日期是 5 号")
    manager = ProjectDecisionVersionManager(
        _store(),
        llm_client=FailingDecisionJudgeLLM(),
    )

    decision = manager.detect_update(
        new,
        [asdict(old.to_memory_core())],
        detection_source="semantic",
    )

    assert not decision.should_supersede
    assert decision.should_reuse_existing
    assert decision.old_memory_id == "mem-old"
    assert decision.reason == "same_scope_topic_and_same_decision"


def test_detect_update_allows_llm_duplicate_when_semantic_candidate_topic_differs() -> None:
    old = _decision(
        "mem-old",
        topic="技术路线讨论",
        decision_text="采用方案 B，而不是方案 A，因为接入成本更低",
    )
    new = _decision(
        "mem-new",
        topic="方案选型结论",
        decision_text="决定采用方案 B，而非方案 A，因为接入成本更低",
    )
    manager = ProjectDecisionVersionManager(
        _store(),
        llm_client=FakeDecisionJudgeLLM(
            [
                {
                    "label": "duplicate",
                    "confidence": 0.95,
                    "reason": "topic 不同，但结论相同",
                }
            ]
        ),
    )

    decision = manager.detect_update(
        new,
        [asdict(old.to_memory_core())],
        detection_source="semantic",
    )

    assert decision.should_reuse_existing
    assert not decision.should_supersede
    assert decision.old_memory_id == "mem-old"
    assert decision.reason == "llm_duplicate"


def test_detect_update_falls_back_to_exact_duplicate_when_llm_fails_and_topic_differs() -> None:
    old = _decision(
        "mem-old",
        topic="技术路线讨论",
        decision_text="确认截止日期是 5 号",
    )
    new = _decision(
        "mem-new",
        topic="发布时间安排",
        decision_text="确认截止日期是 5 号",
    )
    manager = ProjectDecisionVersionManager(
        _store(),
        llm_client=FailingDecisionJudgeLLM(),
    )

    decision = manager.detect_update(
        new,
        [asdict(old.to_memory_core())],
        detection_source="semantic",
    )

    assert not decision.should_supersede
    assert decision.should_reuse_existing
    assert decision.old_memory_id == "mem-old"
    assert decision.reason == "same_scope_decision_and_same_decision"


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
