from __future__ import annotations

from src.domains.project_decision.models import ProjectDecision
from src.proactive.decider import ProjectDecisionProactiveDecider
from src.schemas import EventContext, NormalizedEvent


class FakeLLMClient:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def ajson(self, system_prompt: str | None, user_prompt: str, **kwargs: object) -> dict[str, object]:
        self.calls.append({"system_prompt": system_prompt or "", "user_prompt": user_prompt, "kwargs": kwargs})
        return self.response


def _event() -> NormalizedEvent:
    return NormalizedEvent(
        event_id="event-1",
        event_type="chat_message",
        source_type="feishu_chat",
        occurred_at="2026-05-05T00:00:00Z",
        context=EventContext(project_id="project-1", team_id="team-1", workspace_id="workspace-1"),
        content_text="继续讨论 SQLite 迁移方案",
    )


def _memory() -> ProjectDecision:
    return ProjectDecision(
        decision_id="mem-1",
        project_id="project-1",
        workspace_id="workspace-1",
        team_id="team-1",
        topic="SQLite 迁移",
        decision="采用 SQLite 原生迁移",
        conclusion="采用 SQLite 原生迁移",
    )


def test_decider_requires_explicit_confidence() -> None:
    llm = FakeLLMClient({"push": True, "reason": "looks related"})
    decider = ProjectDecisionProactiveDecider(llm, min_confidence=0.8)

    decision = decider.decide(_event(), _memory(), [{"memory_id": "mem-2", "summary_text": "SQLite 选型"}])

    assert decision.should_push is False
    assert decision.confidence == 0.0


def test_decider_prompt_includes_related_memories() -> None:
    llm = FakeLLMClient({"push": True, "confidence": 0.9, "reason": "directly related"})
    decider = ProjectDecisionProactiveDecider(llm, min_confidence=0.8)

    decision = decider.decide(_event(), _memory(), [{"memory_id": "mem-2", "summary_text": "SQLite 选型"}])

    assert decision.should_push is True
    assert "mem-2" in str(llm.calls[0]["user_prompt"])
