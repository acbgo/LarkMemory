from __future__ import annotations

from src.domains.team_retention import TeamRetentionExtractor
from src.schemas import EventContext, NormalizedEvent


def _event(content_text: str, payload: dict[str, object] | None = None) -> NormalizedEvent:
    return NormalizedEvent(
        event_id="event-1",
        event_type="chat_message",
        source_type="feishu_chat",
        occurred_at="2026-04-27T00:00:00Z",
        context=EventContext(team_id="team-1", project_id="project-1", workspace_id="workspace-1"),
        content_text=content_text,
        payload=payload or {},
    )


def test_extracts_team_retention_memory_from_explicit_text() -> None:
    candidates = TeamRetentionExtractor().extract(
        _event("请团队长期记住：客户 A 要求所有导出文件使用 xlsx，不接受 csv。")
    )

    assert len(candidates) == 1
    memory = candidates[0].memory
    assert memory.team_id == "team-1"
    assert memory.fact_type == "customer_preference"
    assert memory.risk_level == "medium"
    assert "xlsx" in memory.fact_value
    assert memory.review_policy == "ebbinghaus"


def test_extracts_from_payload_fields() -> None:
    candidates = TeamRetentionExtractor().extract(
        _event(
            "普通消息",
            payload={
                "memory_intent": "team_retention",
                "fact_type": "api_key",
                "fact_value": "API key 已更新到 secret-v2",
                "risk_level": "high",
                "owner": "ops",
            },
        )
    )

    assert len(candidates) == 1
    assert candidates[0].memory.fact_type == "api_key"
    assert candidates[0].memory.owner == "ops"
    assert candidates[0].memory.risk_level == "high"


def test_without_retention_signal_returns_empty_list() -> None:
    assert TeamRetentionExtractor().extract(_event("下午同步一下项目状态")) == []
