from __future__ import annotations

from src.domains.project_decision import ProjectDecisionExtractor
from src.schemas import EventContext, NormalizedEvent


class FakeExtractionLLM:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    async def ajson(self, system_prompt: str | None, user_prompt: str, **kwargs: object) -> dict[str, object]:
        self.calls.append({"system_prompt": system_prompt or "", "user_prompt": user_prompt, "kwargs": kwargs})
        return self.payload


def _event(
    *,
    content_text: str | None,
    payload: dict[str, object] | None = None,
) -> NormalizedEvent:
    return NormalizedEvent(
        event_id="event-1",
        event_type="chat_message",
        source_type="feishu_chat",
        occurred_at="2026-04-26T08:00:00Z",
        context=EventContext(
            project_id="project-1",
            team_id="team-1",
            workspace_id="workspace-1",
            thread_id="thread-1",
        ),
        content_text=content_text,
        payload=payload or {},
        tags=["demo"],
    )


def test_extracts_confirmed_decision_with_alternatives_and_reason() -> None:
    candidates = ProjectDecisionExtractor().extract(
        _event(content_text="我们决定采用方案 B 而不是方案 A，因为接入成本更低")
    )

    assert len(candidates) == 1
    decision = candidates[0].decision
    assert decision.status == "confirmed"
    assert decision.project_id == "project-1"
    assert decision.topic == "方案选择"
    assert len(decision.alternatives) == 2
    assert {item.name for item in decision.alternatives} == {"方案 A", "方案 B"}
    assert decision.reasons[0].text.startswith("接入成本更低")


def test_extracts_deadline_decision() -> None:
    candidates = ProjectDecisionExtractor().extract(
        _event(content_text="上周五确认截止日期是 5 号")
    )

    assert candidates
    assert candidates[0].decision.topic == "截止日期"
    assert "5 号" in candidates[0].decision.decision


def test_chat_without_decision_signal_returns_empty_list() -> None:
    candidates = ProjectDecisionExtractor().extract(
        _event(content_text="大家下午同步一下状态，辛苦确认参会")
    )

    assert candidates == []


def test_extracts_from_payload_text_when_content_text_is_empty() -> None:
    candidates = ProjectDecisionExtractor().extract(
        _event(content_text=None, payload={"text": "确认采用方案 B，因为实现成本低"})
    )

    assert len(candidates) == 1
    assert "方案 B" in candidates[0].decision.decision


def test_low_confidence_candidate_is_filtered_by_threshold() -> None:
    candidates = ProjectDecisionExtractor(min_confidence=0.9).extract(
        _event(content_text="讨论结论暂时不明确，后续再看")
    )

    assert candidates == []


def test_llm_extracts_structured_decision_without_rule_signal() -> None:
    llm = FakeExtractionLLM(
        {
            "memories": [
                {
                    "topic": "search backend",
                    "content": "use SQLite first",
                    "confidence": 0.92,
                }
            ],
        }
    )

    candidates = ProjectDecisionExtractor(llm_client=llm).extract(
        _event(content_text="team aligned on SQLite first for the local demo")
    )

    assert len(candidates) == 1
    assert candidates[0].decision.topic == "search backend"
    assert candidates[0].decision.decision == "use SQLite first"
    assert candidates[0].decision.confidence == 0.92
    assert len(llm.calls) == 1
