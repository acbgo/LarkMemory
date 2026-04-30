from __future__ import annotations

from src.domains.project_decision import (
    ProjectDecision,
    ProjectDecisionCandidate,
)


def _decision() -> ProjectDecision:
    return ProjectDecision(
        decision_id="mem-decision-1",
        project_id="project-1",
        workspace_id="workspace-1",
        team_id="team-1",
        thread_id="thread-1",
        topic="检索层方案",
        decision="采用方案 B",
        stage="技术选型",
        alternatives=["方案 A", "方案 B"],
        reasons=["接入成本更低"],
        objections=["方案 A 接入成本更高"],
        source_event_id="event-1",
        source_type="feishu_chat",
        source_ref="message-1",
        decided_at="2026-04-26T00:00:00Z",
        confidence=1.4,
        importance=-0.2,
    )


def test_project_decision_content_and_summary_include_core_fields() -> None:
    decision = _decision()

    content = decision.build_content_text()
    summary = decision.build_summary_text()

    assert "检索层方案" in content
    assert "采用方案 B" in content
    assert "接入成本更低" in content
    assert "方案 A" in content
    assert "方案 A 接入成本更高" in content
    assert len(summary) <= 200
    assert "采用方案 B" in summary


def test_project_decision_to_memory_core_maps_domain_and_clamps_scores() -> None:
    memory = _decision().to_memory_core()

    assert memory.domain == "project_decision"
    assert memory.memory_type == "project_decision"
    assert memory.scope == "project"
    assert memory.source_ref == "message-1"
    assert "project_id:project-1" in memory.entities
    assert "topic:检索层方案" in memory.entities
    assert "stage:技术选型" in memory.tags
    assert memory.confidence == 1.0
    assert memory.importance == 0.0


def test_project_decision_from_memory_core_accepts_dataclass_and_dict() -> None:
    memory = _decision().to_memory_core()

    from_dataclass = ProjectDecision.from_memory_core(memory)
    from_dict = ProjectDecision.from_memory_core(
        {
            "memory_id": memory.memory_id,
            "domain": memory.domain,
            "memory_type": memory.memory_type,
            "scope": memory.scope,
            "source_type": memory.source_type,
            "source_ref": memory.source_ref,
            "content_text": memory.content_text,
            "summary_text": memory.summary_text,
            "entities_json": memory.entities,
            "tags_json": memory.tags,
            "importance": memory.importance,
            "confidence": memory.confidence,
            "status": memory.status,
            "valid_from": memory.valid_from,
            "overwrite_of": memory.overwrite_of,
            "superseded_by": memory.superseded_by,
            "created_at": memory.created_at,
        }
    )

    assert from_dataclass.topic == "检索层方案"
    assert from_dataclass.project_id == "project-1"
    assert from_dict.decision == "采用方案 B"
    assert from_dict.stage == "技术选型"
    assert "接入成本更低" in from_dict.reasons


def test_project_decision_candidate_admission_boundaries() -> None:
    accepted = ProjectDecisionCandidate(
        decision=_decision(),
        evidence_text="我们决定采用方案 B",
        signals=["决定"],
    )
    low_confidence = ProjectDecisionCandidate(
        decision=ProjectDecision(topic="方案", decision="采用 A", confidence=0.1),
        evidence_text="采用 A",
        signals=["采用"],
    )
    missing_topic = ProjectDecisionCandidate(
        decision=ProjectDecision(topic="", decision="采用 A", confidence=0.9),
        evidence_text="采用 A",
        signals=["采用"],
    )

    assert accepted.is_admissible()
    assert not low_confidence.is_admissible()
    assert not missing_topic.is_admissible()
