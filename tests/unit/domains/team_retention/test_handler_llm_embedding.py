from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from src.core.domain_handler import DomainRuntime
from src.domains.team_retention.handler import TeamRetentionDomainHandler
from src.domains.team_retention.llm_extractor import _json_schema
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


class RaisingEmbeddingStore(FakeEmbeddingStore):
    def upsert_embedding(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("chroma down")

    def query_similar(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        raise RuntimeError("chroma query down")


class RaisingEmbeddingClient:
    def embed_text(self, text: str) -> list[float]:
        raise RuntimeError("embedding model down")


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


def _semantic_response(
    *,
    is_candidate: bool = True,
    fact_type: str = "customer_preference",
    fact_value: str = "客户 A 要求所有导出文件使用 xlsx，不接受 csv",
    certainty: str = "explicit",
    stability: str = "stable",
    actionability: str = "actionable",
    risk_level_hint: str = "medium",
    needs_confirmation: bool = False,
    update_intent: str = "none",
    update_signal_text: str | None = None,
    evidence_text: str | None = None,
    primary_entity: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "is_team_retention_candidate": is_candidate,
        "fact_type": fact_type,
        "fact_value": fact_value,
        "summary": "客户 A 导出格式要求",
        "primary_entity": primary_entity
        or {
            "type": "customer",
            "name": "客户 A",
            "normalized_key": "customer-a",
        },
        "owner_hint": None,
        "risk_level_hint": risk_level_hint,
        "validity": {
            "valid_from": None,
            "valid_to": None,
            "is_temporary": stability == "temporary",
        },
        "certainty": certainty,
        "stability": stability,
        "actionability": actionability,
        "update_intent": update_intent,
        "update_signal_text": update_signal_text,
        "needs_confirmation": needs_confirmation,
        "confirmation_reason": "表达依赖上下文" if needs_confirmation else None,
        "evidence_text": evidence_text or fact_value,
        "reason": "这是会影响团队后续交付的客户约束。",
    }


def test_vector_hit_same_entity_different_topic_does_not_supersede_old_active() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        old = TeamRetentionMemory(
            retention_id="mem-old-export",
            team_id="team-1",
            project_id="project-1",
            workspace_id="workspace-1",
            fact_type="customer_preference",
            fact_value="客户 A 要求导出 xlsx，不接受 csv",
            risk_level="medium",
            version_group="team-1:customer_preference:customer-a:export-format",
            confidence=0.9,
            importance=0.8,
        )
        memory_store.insert_memory_core(old.to_memory_core())
        team_store.insert_memory(old)
        team_store.create_review_schedule(old)
        llm = FakeLLMClient(
            _semantic_response(
                fact_value="客户 A 现在对接渠道改为飞书群，不再走邮件。",
                update_intent="supersede",
                update_signal_text="改为",
                evidence_text="客户 A 现在对接渠道改为飞书群，不再走邮件。",
                primary_entity={"type": "customer", "name": "客户 A", "normalized_key": "customer-a"},
            )
            | {"topic_key": "contact-channel"}
        )
        embedding_store = FakeEmbeddingStore(
            query_hits=[{"memory_id": "mem-old-export", "distance": 0.1, "metadata": {"status": "active"}}]
        )
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )

        result = handler.ingest_event(_event("客户 A 现在对接渠道改为飞书群，不再走邮件。"), runtime)

        assert memory_store.get_memory("mem-old-export")["status"] == "active"
        assert team_store.get_review_schedule("mem-old-export").active is True
        assert result.memory_ids == ["mem-old-export"] or memory_store.get_memory(result.memory_ids[0])["status"] in {"active", "candidate"}
        if result.memory_ids != ["mem-old-export"]:
            assert memory_store.get_memory(result.memory_ids[0])["overwrite_of"] is None
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_active_supersede_of_old_candidate_keeps_new_memory_active() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        old = TeamRetentionMemory(
            retention_id="mem-old-candidate",
            team_id="team-1",
            project_id="project-1",
            workspace_id="workspace-1",
            fact_type="customer_preference",
            fact_value="客户 A 可能不接受 csv，待确认",
            risk_level="medium",
            version_group="team-1:customer_preference:customer-a:export-format",
            confidence=0.5,
            importance=0.5,
            metadata={"needs_confirmation": True},
        )
        old_core = old.to_memory_core()
        old_core.status = "candidate"  # type: ignore[assignment]
        memory_store.insert_memory_core(old_core)
        team_store.insert_memory(old)
        llm = FakeLLMClient(
            _semantic_response(
                fact_value="客户 A 明确要求导出使用 xlsx，不接受 csv。",
                update_intent="supersede",
                update_signal_text="明确要求",
                evidence_text="客户 A 明确要求导出使用 xlsx，不接受 csv。",
            )
            | {"topic_key": "export-format"}
        )
        embedding_store = FakeEmbeddingStore(
            query_hits=[{"memory_id": "mem-old-candidate", "distance": 0.1, "metadata": {"status": "candidate"}}]
        )
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )

        result = handler.ingest_event(_event("客户 A 明确要求导出使用 xlsx，不接受 csv。"), runtime)

        new_id = result.memory_ids[0]
        assert new_id != "mem-old-candidate"
        assert memory_store.get_memory(new_id)["status"] == "active"
        assert team_store.get_review_schedule(new_id) is not None
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_llm_json_schema_excludes_legacy_decision_and_score_fields() -> None:
    schema = _json_schema()

    properties = schema["properties"]
    assert "decision" not in properties
    assert "score_breakdown" not in properties
    assert "importance" not in properties
    assert "confidence" not in properties


def test_legacy_llm_fields_are_ignored_by_admission() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        response = _semantic_response(
            certainty="speculative",
            needs_confirmation=True,
            evidence_text="客户 A 可能以后不接受 csv，待确认。",
        )
        response.update(
            {
                "decision": "active",
                "importance": 1.0,
                "confidence": 1.0,
                "score_breakdown": {"explicit_intent": 1.0, "stability": 1.0},
            }
        )
        llm = FakeLLMClient(response)
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=FakeEmbeddingStore(),  # type: ignore[arg-type]
        )

        result = handler.ingest_event(_event("客户 A 可能以后不接受 csv，待确认。"), runtime)

        assert memory_store.get_memory(result.memory_ids[0])["status"] == "candidate"
        assert team_store.get_review_schedule(result.memory_ids[0]) is None
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_prompt_states_llm_is_not_final_admission_judge() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(_semantic_response(needs_confirmation=True))
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=FakeEmbeddingStore(),  # type: ignore[arg-type]
        )

        handler.ingest_event(_event(), runtime)

        system_prompt = llm.calls[0]["system_prompt"]
        user_prompt = llm.calls[0]["user_prompt"]
        assert "不负责最终入库准入" in system_prompt
        assert "不要输出重要性分数" in system_prompt
        assert "复习计划" in system_prompt
        assert "覆盖旧记忆" in system_prompt
        assert "不要打分，不要决定最终状态" in user_prompt
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_llm_does_not_need_score_or_importance_for_active_admission() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(_semantic_response())
        embedding_store = FakeEmbeddingStore()
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )

        result = handler.ingest_event(_event("请团队长期记住：客户 A 后续导出必须使用 xlsx，不接受 csv。"), runtime)

        row = memory_store.get_memory(result.memory_ids[0])
        assert row["status"] == "active"
        assert team_store.get_review_schedule(result.memory_ids[0]) is not None
        assert "score_breakdown" not in llm.response
        assert "importance" not in llm.response
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_empty_rule_features_but_clear_text_is_not_rejected() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(
            _semantic_response(
                fact_value="客户 A 不接受 csv 导出。",
                certainty="inferred",
                needs_confirmation=True,
                evidence_text="A 那边导出还是老规矩，别给 csv。",
            )
        )
        embedding_store = FakeEmbeddingStore()
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )

        result = handler.ingest_event(_event("A 那边导出还是老规矩，别给 csv。"), runtime)

        assert len(result.memory_ids) == 1
        row = memory_store.get_memory(result.memory_ids[0])
        assert row["status"] == "candidate"
        assert team_store.get_review_schedule(result.memory_ids[0]) is None
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_rule_keyword_hits_ordinary_chat_cannot_become_active() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(
            _semantic_response(
                is_candidate=True,
                fact_type="team_fact",
                fact_value="下午必须长期看一下这个问题。",
                certainty="speculative",
                stability="temporary",
                actionability="unclear",
                risk_level_hint="low",
                needs_confirmation=True,
                evidence_text="以后必须长期看一下。",
            )
        )
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=FakeEmbeddingStore(),  # type: ignore[arg-type]
        )

        result = handler.ingest_event(_event("以后必须长期看一下。"), runtime)

        if result.memory_ids:
            assert memory_store.get_memory(result.memory_ids[0])["status"] == "candidate"
            assert team_store.get_review_schedule(result.memory_ids[0]) is None
        else:
            assert result.candidate_count == 0
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_speculative_or_needs_confirmation_cannot_be_active() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(
            _semantic_response(
                certainty="speculative",
                needs_confirmation=True,
                evidence_text="客户 A 可能以后不接受 csv，待确认。",
            )
        )
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=FakeEmbeddingStore(),  # type: ignore[arg-type]
        )

        result = handler.ingest_event(_event("客户 A 可能以后不接受 csv，待确认。"), runtime)

        assert len(result.memory_ids) == 1
        assert memory_store.get_memory(result.memory_ids[0])["status"] == "candidate"
        assert team_store.get_review_schedule(result.memory_ids[0]) is None
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_prompt_hides_internal_ids_from_llm() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(_semantic_response(needs_confirmation=True))
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=FakeEmbeddingStore(),  # type: ignore[arg-type]
        )

        handler.ingest_event(_event(), runtime)

        prompt = llm.calls[0]["user_prompt"]
        assert "event_id" not in prompt
        assert "team-1" not in prompt
        assert "project-1" not in prompt
        assert "workspace-1" not in prompt
        assert "thread_id" not in prompt
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_sensitive_policy_is_not_hardcoded_in_prompt() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(_semantic_response(needs_confirmation=True))
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=FakeEmbeddingStore(),  # type: ignore[arg-type]
        )

        handler.ingest_event(_event("请团队长期记住：api key = sk-secretsecret 已更新。"), runtime)

        system_prompt = llm.calls[0]["system_prompt"]
        assert "Do not preserve raw secrets" not in system_prompt
        assert "raw secrets" not in system_prompt
        assert "是否脱敏由后端策略决定" in system_prompt
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_candidate_update_signal_does_not_supersede_old_active_memory() -> None:
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
            _semantic_response(
                fact_value="客户 A 现在接受 csv",
                certainty="inferred",
                needs_confirmation=True,
                update_intent="supersede",
                update_signal_text="现在",
                evidence_text="客户 A 现在好像接受 csv，待确认。",
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

        result = handler.ingest_event(_event("客户 A 现在好像接受 csv，待确认。"), runtime)

        assert memory_store.get_memory("mem-old")["status"] == "active"
        assert team_store.get_review_schedule("mem-old").active is True
        assert memory_store.get_memory(result.memory_ids[0])["status"] == "candidate"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_active_explicit_update_signal_can_supersede_old_memory() -> None:
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
            _semantic_response(
                fact_value="客户 A 接受 csv，不再要求 xlsx",
                update_intent="supersede",
                update_signal_text="不再",
                evidence_text="客户 A 现在接受 csv，旧 xlsx 不再使用。",
            )
            | {"topic_key": "export-format"}
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

        assert memory_store.get_memory("mem-old")["status"] == "superseded"
        assert memory_store.get_memory(result.memory_ids[0])["status"] == "active"
        assert team_store.get_review_schedule("mem-old").active is False
        assert team_store.get_review_schedule(result.memory_ids[0]) is not None
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_llm_candidate_is_stored_and_indexed_but_not_scheduled() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(_semantic_response(needs_confirmation=True))
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
        llm = FakeLLMClient(_semantic_response())
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
        llm = FakeLLMClient(_semantic_response(is_candidate=False, fact_value="", evidence_text=""))
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
            _semantic_response(
                fact_value="客户 A 要求导出 csv",
            )
            | {"topic_key": "export-format"}
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
        llm = FakeLLMClient(_semantic_response(needs_confirmation=True))
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
            _semantic_response(
                fact_value="客户 A 现在接受 csv，旧 xlsx 不再使用",
                update_intent="supersede",
                update_signal_text="不再",
            )
            | {"topic_key": "export-format"}
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
        llm = FakeLLMClient(_semantic_response(needs_confirmation=True))
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
        llm = FakeLLMClient(_semantic_response(needs_confirmation=True))
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


def test_embedding_index_failure_does_not_break_memory_ingest() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(_semantic_response())
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=RaisingEmbeddingStore(),  # type: ignore[arg-type]
            embedding_client=RaisingEmbeddingClient(),  # type: ignore[arg-type]
        )

        result = handler.ingest_event(_event(), runtime)

        assert len(result.memory_ids) == 1
        assert memory_store.get_memory(result.memory_ids[0])["status"] == "active"
        assert team_store.get_memory(result.memory_ids[0]) is not None
        assert team_store.get_review_schedule(result.memory_ids[0]) is not None
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
        response = _semantic_response(
            fact_value="客户 A 接受 csv",
            update_intent="supersede",
            update_signal_text="不再",
        )
        response["topic_key"] = "export-format"
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
