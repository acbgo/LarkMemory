from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from src.core.domain_handler import DomainRuntime
from src.domains.team_retention.handler import TeamRetentionDomainHandler
from src.domains.team_retention.models import TeamRetentionMemory
from src.schemas import EventContext, NormalizedEvent
from src.storage import MemoryCoreStore, TeamRetentionStore


class FakeLLMClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def ajson(
        self,
        system_prompt: str | None,
        user_prompt: str,
        *,
        schema: dict[str, Any] | None = None,
        temperature: float | None = 0,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "schema": schema,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "kwargs": kwargs,
            }
        )
        return self.response


class RaisingLLMClient:
    def __init__(self) -> None:
        self.calls = 0

    async def ajson(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        raise ValueError("bad json")


class FakeEmbeddingStore:
    def __init__(self, query_hits: list[dict[str, Any]] | None = None) -> None:
        self.upserts: list[dict[str, Any]] = []
        self.queries: list[dict[str, Any]] = []
        self.query_hits = query_hits or []

    def upsert_embedding(
        self,
        memory_id: str,
        text: str,
        metadata: dict[str, Any],
        embedding: list[float] | None = None,
    ) -> None:
        self.upserts.append(
            {
                "memory_id": memory_id,
                "text": text,
                "metadata": metadata,
                "embedding": embedding,
            }
        )

    def query_similar(
        self,
        text: str,
        domain: str | None = None,
        *,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.queries.append(
            {
                "text": text,
                "domain": domain,
                "top_k": top_k,
                "filters": filters,
            }
        )
        return list(self.query_hits)


def _stores() -> tuple[MemoryCoreStore, TeamRetentionStore, Path]:
    root = Path.cwd() / ".tmp-tests"
    root.mkdir(exist_ok=True)
    temp_dir = root / f"team-retention-handler-{uuid.uuid4().hex}"
    temp_dir.mkdir()
    db_path = str(temp_dir / "memory.db")
    memory_store = MemoryCoreStore(db_path)
    memory_store.create_table()
    team_store = TeamRetentionStore(db_path)
    team_store.create_table()
    return memory_store, team_store, temp_dir


def _event(content_text: str = "客户 A 后续导出必须使用 xlsx，不接受 csv。") -> NormalizedEvent:
    return NormalizedEvent(
        event_id=f"event-{uuid.uuid4().hex}",
        event_type="chat_message",
        source_type="feishu_chat",
        occurred_at="2026-04-30T00:00:00Z",
        context=EventContext(team_id="team-1", project_id="project-1", workspace_id="workspace-1"),
        content_text=content_text,
        payload={},
    )


def _llm_response(
    *,
    decision: str,
    fact_value: str = "客户 A 要求所有导出文件使用 xlsx，不接受 csv",
    confidence: float = 0.82,
    score: float = 0.82,
) -> dict[str, Any]:
    return {
        "decision": decision,
        "is_team_retention_memory": decision != "reject",
        "fact_type": "customer_preference",
        "fact_value": fact_value,
        "summary": "客户 A 导出格式要求",
        "primary_entity": {
            "type": "customer",
            "name": "客户 A",
            "normalized_key": "customer-a",
        },
        "topic_key": "export-format",
        "owner": None,
        "risk_level": "medium",
        "valid_from": None,
        "valid_to": None,
        "review_policy": "ebbinghaus",
        "confidence": confidence,
        "importance": 0.78,
        "score_breakdown": {
            "explicit_intent": score,
            "future_dependency": score,
            "cross_member_dependency": score,
            "risk_or_cost": score,
            "source_authority": score,
            "stability": score,
            "actionability": score,
            "uncertainty_penalty": 0.0,
            "sensitivity_penalty": 0.0,
            "triviality_penalty": 0.0,
        },
        "needs_confirmation": decision == "candidate",
        "reason": "客户长期交付偏好会影响后续团队交付。",
        "evidence_text": fact_value,
        "version_group_hint": "customer-a:export-format",
    }


def test_llm_candidate_is_stored_and_indexed_but_not_scheduled() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(_llm_response(decision="candidate", confidence=0.65, score=0.65))
        embedding_store = FakeEmbeddingStore()
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )

        result = handler.ingest_event(_event(), runtime)

        assert len(llm.calls) == 1
        assert len(result.memory_ids) == 1
        row = memory_store.get_memory(result.memory_ids[0])
        assert row["status"] == "candidate"
        assert team_store.get_review_schedule(result.memory_ids[0]) is None
        assert embedding_store.upserts[0]["memory_id"] == result.memory_ids[0]
        assert embedding_store.upserts[0]["metadata"]["status"] == "candidate"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_llm_active_is_stored_indexed_and_scheduled() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(_llm_response(decision="active", confidence=0.9, score=0.9))
        embedding_store = FakeEmbeddingStore()
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )

        result = handler.ingest_event(_event(), runtime)

        row = memory_store.get_memory(result.memory_ids[0])
        assert row["status"] == "active"
        assert team_store.get_review_schedule(result.memory_ids[0]) is not None
        assert embedding_store.upserts[0]["metadata"]["status"] == "active"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_llm_reject_does_not_store_or_index_memory() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(_llm_response(decision="reject", confidence=0.1, score=0.1))
        embedding_store = FakeEmbeddingStore()
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )

        result = handler.ingest_event(_event("收到，下午同步。"), runtime)

        assert result.memory_ids == []
        assert result.candidate_count == 0
        assert memory_store.list_active_memories(domain="team_retention") == []
        assert embedding_store.upserts == []
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_vector_similar_changed_fact_becomes_conflict_candidate_without_schedule() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        old = TeamRetentionMemory(
            retention_id="mem-old",
            team_id="team-1",
            project_id="project-1",
            workspace_id="workspace-1",
            fact_type="customer_preference",
            fact_value="客户 A 要求导出 xlsx",
            risk_level="medium",
            version_group="team-1:customer_preference:customer-a:export-format",
            confidence=0.9,
            importance=0.8,
        )
        memory_store.insert_memory_core(old.to_memory_core())
        team_store.insert_memory(old)
        team_store.create_review_schedule(old)
        llm = FakeLLMClient(
            _llm_response(
                decision="active",
                fact_value="客户 A 要求导出 csv",
                confidence=0.9,
                score=0.9,
            )
        )
        embedding_store = FakeEmbeddingStore(
            query_hits=[
                {
                    "memory_id": "mem-old",
                    "distance": 0.1,
                    "metadata": {
                        "domain": "team_retention",
                        "status": "active",
                        "team_id": "team-1",
                        "project_id": "project-1",
                    },
                }
            ]
        )
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )

        result = handler.ingest_event(_event("客户 A 要求导出 csv。"), runtime)

        assert embedding_store.queries, "lifecycle should query vector candidates"
        assert len(result.memory_ids) == 1
        new_id = result.memory_ids[0]
        row = memory_store.get_memory(new_id)
        assert row["status"] == "candidate"
        assert team_store.get_review_schedule(new_id) is None
        memory = team_store.get_memory(new_id)
        assert memory is not None
        assert memory.metadata["conflict_with"] == "mem-old"
        assert memory.metadata["needs_confirmation"] is True
        assert team_store.get_review_schedule("mem-old").active is True
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_repeated_candidate_reinforces_without_requiring_review_schedule() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(_llm_response(decision="candidate", confidence=0.65, score=0.65))
        embedding_store = FakeEmbeddingStore()
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )

        first = handler.ingest_event(_event(), runtime)
        second = handler.ingest_event(_event(), runtime)

        assert first.memory_ids == second.memory_ids
        memory_id = first.memory_ids[0]
        assert memory_store.get_memory(memory_id)["status"] == "candidate"
        assert team_store.get_review_schedule(memory_id) is None
        reinforced = team_store.get_memory(memory_id)
        assert reinforced is not None
        assert reinforced.metadata["reinforce_count"] == 1
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_explicit_update_signal_supersedes_old_active_memory() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        old = TeamRetentionMemory(
            retention_id="mem-old",
            team_id="team-1",
            project_id="project-1",
            workspace_id="workspace-1",
            fact_type="customer_preference",
            fact_value="客户 A 要求导出 xlsx",
            risk_level="medium",
            version_group="team-1:customer_preference:customer-a:export-format",
            confidence=0.9,
            importance=0.8,
        )
        memory_store.insert_memory_core(old.to_memory_core())
        team_store.insert_memory(old)
        team_store.create_review_schedule(old)
        llm = FakeLLMClient(
            _llm_response(
                decision="active",
                fact_value="客户 A 现在接受 csv，旧 xlsx 不再使用",
                confidence=0.9,
                score=0.9,
            )
        )
        embedding_store = FakeEmbeddingStore(
            query_hits=[{"memory_id": "mem-old", "distance": 0.1, "metadata": {"status": "active"}}]
        )
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )

        result = handler.ingest_event(_event("客户 A 现在接受 csv，旧 xlsx 不再使用。"), runtime)

        new_id = result.memory_ids[0]
        assert new_id != "mem-old"
        assert memory_store.get_memory("mem-old")["status"] == "superseded"
        assert memory_store.get_memory(new_id)["status"] == "active"
        assert team_store.get_review_schedule("mem-old").active is False
        assert team_store.get_review_schedule(new_id) is not None
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_llm_prompt_does_not_include_raw_secret_payload() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(_llm_response(decision="candidate", confidence=0.65, score=0.65))
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=FakeEmbeddingStore(),  # type: ignore[arg-type]
        )
        event = _event("请团队长期记住：api key = sk-secretsecret 已更新。")
        event.payload["api_key"] = "sk-payloadsecret"
        event.payload["safe_hint"] = "keep"

        handler.ingest_event(event, runtime)

        prompt = llm.calls[0]["user_prompt"]
        assert "sk-secretsecret" not in prompt
        assert "sk-payloadsecret" not in prompt
        assert "[REDACTED]" in prompt
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_embedding_metadata_filters_none_values() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(_llm_response(decision="candidate", confidence=0.65, score=0.65))
        embedding_store = FakeEmbeddingStore()
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        event = NormalizedEvent(
            event_id="event-no-scope",
            event_type="chat_message",
            source_type="feishu_chat",
            occurred_at="2026-04-30T00:00:00Z",
            context=EventContext(team_id="team-1"),
            content_text="客户 A 后续导出必须使用 xlsx。",
            payload={},
        )

        handler.ingest_event(event, runtime)

        metadata = embedding_store.upserts[0]["metadata"]
        assert "project_id" not in metadata
        assert "workspace_id" not in metadata
        assert all(value is not None for value in metadata.values())
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_llm_failure_fallback_preserves_rule_version_supersede() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        old_event = _event("请团队长期记住：客户 A 要求所有导出文件使用 xlsx。")
        old_event.payload.update(
            {
                "memory_intent": "team_retention",
                "fact_type": "customer_preference",
                "fact_value": "客户 A 要求导出 xlsx",
                "version_group": "team-1:customer-a-export-format",
            }
        )
        fallback_llm = RaisingLLMClient()
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=fallback_llm)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=FakeEmbeddingStore(),  # type: ignore[arg-type]
        )

        first = handler.ingest_event(old_event, runtime)
        new_event = _event("请团队长期记住：客户 A 现在接受 csv，但必须 UTF-8 编码。")
        new_event.payload.update(
            {
                "memory_intent": "team_retention",
                "fact_type": "customer_preference",
                "fact_value": "客户 A 现在接受 csv，但必须 UTF-8 编码",
                "version_group": "team-1:customer-a-export-format",
            }
        )
        second = handler.ingest_event(new_event, runtime)

        assert fallback_llm.calls == 2
        assert len(first.memory_ids) == 1
        assert len(second.memory_ids) == 1
        assert first.memory_ids[0] != second.memory_ids[0]
        assert memory_store.get_memory(first.memory_ids[0])["status"] == "superseded"
        assert memory_store.get_memory(second.memory_ids[0])["status"] == "active"
        assert team_store.get_review_schedule(first.memory_ids[0]).active is False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_supersede_signal_from_evidence_text_updates_old_memory() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        old = TeamRetentionMemory(
            retention_id="mem-old",
            team_id="team-1",
            project_id="project-1",
            workspace_id="workspace-1",
            fact_type="customer_preference",
            fact_value="客户 A 要求导出 xlsx",
            risk_level="medium",
            version_group="team-1:customer_preference:customer-a:export-format",
            confidence=0.9,
            importance=0.8,
        )
        memory_store.insert_memory_core(old.to_memory_core())
        team_store.insert_memory(old)
        team_store.create_review_schedule(old)
        response = _llm_response(
            decision="active",
            fact_value="客户 A 接受 csv",
            confidence=0.9,
            score=0.9,
        )
        response["evidence_text"] = "客户 A 现在接受 csv，旧 xlsx 不再使用。"
        llm = FakeLLMClient(response)
        embedding_store = FakeEmbeddingStore(
            query_hits=[{"memory_id": "mem-old", "distance": 0.1, "metadata": {"status": "active"}}]
        )
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )

        result = handler.ingest_event(_event("客户 A 现在接受 csv，旧 xlsx 不再使用。"), runtime)

        assert memory_store.get_memory("mem-old")["status"] == "superseded"
        assert memory_store.get_memory(result.memory_ids[0])["status"] == "active"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
