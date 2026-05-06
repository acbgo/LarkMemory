from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from src.core.domain_handler import DomainRuntime
from src.domains.team_retention.handler import TeamRetentionDomainHandler
from src.domains.team_retention.llm_extractor import _json_schema
from src.domains.team_retention.lifecycle import TeamRetentionArbitrationResult
from src.domains.team_retention.models import TeamRetentionMemory
from src.schemas import EventContext, NormalizedEvent
from src.storage import MemoryCoreStore, TeamRetentionStore


class FakeLLMClient:
    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.response = response or {}
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
        return dict(self.response)


class RaisingLLMClient:
    def __init__(self) -> None:
        self.calls = 0

    async def ajson(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        raise ValueError("bad json")


class MockArbitrator:
    def __init__(self, verdicts: list[TeamRetentionArbitrationResult] | None = None) -> None:
        self.verdicts = verdicts or []
        self.call_count = 0
        self.last_new_memory: TeamRetentionMemory | None = None
        self.last_old_memories: list[TeamRetentionMemory] = []

    def load_old_memories(
        self,
        new_memory: TeamRetentionMemory,
        get_memory_fn: Any,
        *,
        top_k: int = 3,
    ) -> list[TeamRetentionMemory]:
        result: list[TeamRetentionMemory] = []
        seen: set[str] = {new_memory.retention_id}
        for hit in _arbitrator_hits:
            mid = hit.get("memory_id") or hit.get("id")
            if isinstance(mid, str) and mid not in seen:
                seen.add(mid)
                old = get_memory_fn(mid)
                if old is not None:
                    result.append(old)
        return result

    def arbitrate(
        self,
        new_memory: TeamRetentionMemory,
        *,
        old_memories: list[TeamRetentionMemory],
    ) -> TeamRetentionArbitrationResult:
        self.call_count += 1
        self.last_new_memory = new_memory
        self.last_old_memories = list(old_memories)
        if self.call_count <= len(self.verdicts):
            return self.verdicts[self.call_count - 1]
        return TeamRetentionArbitrationResult(action="add", reason="mock_fallback_add")


_arbitrator_hits: list[dict[str, Any]] = []


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


class FakeNotifier:
    def __init__(self) -> None:
        self.created_cards: list[tuple[str, dict[str, Any]]] = []
        self.candidate_cards: list[tuple[str, dict[str, Any]]] = []

    def send_team_memory_created(self, chat_id: str, suggestion: dict[str, Any]) -> None:
        self.created_cards.append((chat_id, suggestion))

    def send_candidate_confirmation(self, chat_id: str, suggestion: dict[str, Any]) -> None:
        self.candidate_cards.append((chat_id, suggestion))


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


def _extraction_response(
    *,
    is_team_retention: bool = True,
    fact_type: str = "customer_preference",
    fact_value: str = "客户 A 要求所有导出文件使用 xlsx，不接受 csv",
    certainty: str = "explicit",
    evidence_quality: str = "direct_quote",
    fact_specificity: str = "specific",
    risk_level: str = "medium",
    time_sensitivity: str = "stable",
    scope_impact: str = "project",
    irreversibility: str = "reversible",
    review_policy: str = "ebbinghaus",
    evidence_text: str | None = None,
    primary_entity: dict[str, str] | None = None,
    topic_key: str | None = None,
) -> dict[str, Any]:
    return {
        "is_team_retention": is_team_retention,
        "fact_type": fact_type,
        "fact_value": fact_value,
        "certainty": certainty,
        "evidence_quality": evidence_quality,
        "fact_specificity": fact_specificity,
        "risk_level": risk_level,
        "time_sensitivity": time_sensitivity,
        "scope_impact": scope_impact,
        "irreversibility": irreversibility,
        "review_policy": review_policy,
        "evidence_text": evidence_text or fact_value,
        "reason": "团队需要记住的重要事实。",
        "summary": "客户 A 导出格式要求",
        "primary_entity": primary_entity
        or {
            "type": "customer",
            "name": "客户 A",
            "normalized_key": "customer-a",
        },
        "topic_key": topic_key,
        "owner": None,
        "valid_from": None,
        "valid_to": None,
        "version_group_hint": None,
    }


def _make_arbitrator(verdicts: list[TeamRetentionArbitrationResult] | None = None) -> MockArbitrator:
    return MockArbitrator(verdicts or [])


def _set_arbitrator_hits(hits: list[dict[str, Any]]) -> None:
    global _arbitrator_hits
    _arbitrator_hits = list(hits)


def test_vector_hit_diff_topic_does_not_supersede_old() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        old = TeamRetentionMemory(
            retention_id="mem-old-export",
            team_id="team-1", project_id="project-1", workspace_id="workspace-1",
            fact_type="customer_preference",
            fact_value="客户 A 要求导出 xlsx，不接受 csv",
            risk_level="medium",
            version_group="team-1:customer_preference:customer-a:export-format",
            confidence=0.9, importance=0.8,
        )
        memory_store.insert_memory_core(old.to_memory_core())
        team_store.insert_memory(old)
        team_store.create_review_schedule(old)

        llm = FakeLLMClient(_extraction_response(
            fact_value="客户 A 现在对接渠道改为飞书群，不再走邮件。",
            topic_key="contact-channel",
        ))
        _set_arbitrator_hits([{"memory_id": "mem-old-export", "distance": 0.1}])
        arbitrator = _make_arbitrator([TeamRetentionArbitrationResult(action="add", reason="different_topic")])
        embedding_store = FakeEmbeddingStore()
        handler = TeamRetentionDomainHandler(
            memory_store, team_store, llm_client=llm, arbitrator=arbitrator,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        handler.ingest_event(_event("客户 A 现在对接渠道改为飞书群，不再走邮件。"), runtime)
        assert memory_store.get_memory("mem-old-export")["status"] == "active"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_supersede_old_candidate_keeps_new_active() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        old = TeamRetentionMemory(
            retention_id="mem-old-candidate",
            team_id="team-1", project_id="project-1", workspace_id="workspace-1",
            fact_type="customer_preference",
            fact_value="客户 A 可能不接受 csv，待确认",
            risk_level="medium",
            version_group="team-1:customer_preference:customer-a:export-format",
            confidence=0.5, importance=0.5,
            metadata={"needs_confirmation": True},
        )
        old_core = old.to_memory_core()
        old_core.status = "candidate"  # type: ignore[assignment]
        memory_store.insert_memory_core(old_core)
        team_store.insert_memory(old)

        llm = FakeLLMClient(_extraction_response(
            fact_value="客户 A 明确要求导出使用 xlsx，不接受 csv。",
            topic_key="export-format",
        ))
        _set_arbitrator_hits([{"memory_id": "mem-old-candidate", "distance": 0.1}])
        arbitrator = _make_arbitrator([TeamRetentionArbitrationResult(
            action="update", target_memory_id="mem-old-candidate", reason="new_is_more_certain",
        )])
        embedding_store = FakeEmbeddingStore()
        handler = TeamRetentionDomainHandler(
            memory_store, team_store, llm_client=llm, arbitrator=arbitrator,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        runtime = DomainRuntime(
            memory_store=memory_store, add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        result = handler.ingest_event(_event("客户 A 明确要求导出使用 xlsx，不接受 csv。"), runtime)
        new_id = result.memory_ids[0]
        assert new_id != "mem-old-candidate"
        assert memory_store.get_memory(new_id)["status"] == "active"
        assert team_store.get_review_schedule(new_id) is not None
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_llm_json_schema_excludes_legacy_fields() -> None:
    schema = _json_schema()
    properties = schema["properties"]
    assert "decision" not in properties
    assert "confidence" not in properties
    assert "importance" not in properties
    assert "certainty" in properties
    assert "evidence_quality" in properties
    assert "fact_specificity" in properties


def test_candidate_is_stored_indexed_not_scheduled() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(_extraction_response(certainty="inferred", fact_specificity="general"))
        embedding_store = FakeEmbeddingStore()
        handler = TeamRetentionDomainHandler(
            memory_store, team_store, llm_client=llm,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        runtime = DomainRuntime(
            memory_store=memory_store, add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        result = handler.ingest_event(_event(), runtime)
        assert len(result.memory_ids) == 1
        row = memory_store.get_memory(result.memory_ids[0])
        assert row["status"] == "candidate"
        assert team_store.get_review_schedule(result.memory_ids[0]) is None
        assert embedding_store.upserts[0]["memory_id"] == result.memory_ids[0]
        assert embedding_store.upserts[0]["metadata"]["status"] == "candidate"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_active_is_stored_indexed_and_scheduled() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(_extraction_response())
        embedding_store = FakeEmbeddingStore()
        handler = TeamRetentionDomainHandler(
            memory_store, team_store, llm_client=llm,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        runtime = DomainRuntime(
            memory_store=memory_store, add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        result = handler.ingest_event(_event(), runtime)
        row = memory_store.get_memory(result.memory_ids[0])
        assert row["status"] == "active"
        assert team_store.get_review_schedule(result.memory_ids[0]) is not None
        assert embedding_store.upserts[0]["metadata"]["status"] == "active"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_reject_does_not_store_or_index() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(_extraction_response(is_team_retention=False, fact_value="", evidence_text=""))
        embedding_store = FakeEmbeddingStore()
        handler = TeamRetentionDomainHandler(
            memory_store, team_store, llm_client=llm,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        runtime = DomainRuntime(
            memory_store=memory_store, add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        result = handler.ingest_event(_event("收到，下午同步。"), runtime)
        assert result.memory_ids == []
        assert result.candidate_count == 0
        assert embedding_store.upserts == []
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_administrative_noise_is_rejected() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(_extraction_response(
            is_team_retention=False, fact_type="team_fact",
            fact_value="", evidence_text="",
        ))
        embedding_store = FakeEmbeddingStore()
        handler = TeamRetentionDomainHandler(
            memory_store, team_store, llm_client=llm,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        runtime = DomainRuntime(
            memory_store=memory_store, add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        result = handler.ingest_event(_event("会议室 C 的白板笔已经补充，放在电视柜抽屉里。"), runtime)
        assert result.memory_ids == []
        assert result.candidate_count == 0
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_speculative_cannot_be_active() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(_extraction_response(
            certainty="speculative", evidence_quality="implied", fact_specificity="vague",
        ))
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store, add_memory=memory_store.insert_memory_core,
            embedding_store=FakeEmbeddingStore(),  # type: ignore[arg-type]
        )
        result = handler.ingest_event(_event("客户 A 可能以后不接受 csv，待确认。"), runtime)
        assert len(result.memory_ids) == 1
        assert memory_store.get_memory(result.memory_ids[0])["status"] == "candidate"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_prompt_hides_internal_ids() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(_extraction_response())
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store, add_memory=memory_store.insert_memory_core,
            embedding_store=FakeEmbeddingStore(),  # type: ignore[arg-type]
        )
        handler.ingest_event(_event(), runtime)
        prompt = llm.calls[0]["user_prompt"]
        assert "team-1" not in prompt
        assert "has_team_scope" in prompt
        assert "has_project_scope" in prompt
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_llm_prompt_contains_label_descriptions() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(_extraction_response())
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store, add_memory=memory_store.insert_memory_core,
            embedding_store=FakeEmbeddingStore(),  # type: ignore[arg-type]
        )
        handler.ingest_event(_event(), runtime)
        system_prompt = llm.calls[0]["system_prompt"]
        assert "explicit" in system_prompt
        assert "speculative" in system_prompt
        assert "fact_type" in system_prompt
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_llm_does_not_need_score_for_admission() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(_extraction_response())
        embedding_store = FakeEmbeddingStore()
        handler = TeamRetentionDomainHandler(
            memory_store, team_store, llm_client=llm,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        runtime = DomainRuntime(
            memory_store=memory_store, add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        result = handler.ingest_event(_event("请团队长期记住：客户 A 后续导出必须使用 xlsx。"), runtime)
        row = memory_store.get_memory(result.memory_ids[0])
        assert row["status"] == "active"
        assert team_store.get_review_schedule(result.memory_ids[0]) is not None
        assert "confidence" not in llm.response
        assert "importance" not in llm.response
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_inferred_text_stored_as_candidate() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(_extraction_response(
            certainty="inferred", fact_specificity="general",
        ))
        embedding_store = FakeEmbeddingStore()
        handler = TeamRetentionDomainHandler(
            memory_store, team_store, llm_client=llm,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        runtime = DomainRuntime(
            memory_store=memory_store, add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        result = handler.ingest_event(_event("A 那边导出还是老规矩，别给 csv。"), runtime)
        assert len(result.memory_ids) == 1
        assert memory_store.get_memory(result.memory_ids[0])["status"] == "candidate"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_arbitration_candidate_does_not_supersede_old() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        old = TeamRetentionMemory(
            retention_id="mem-old", team_id="team-1", project_id="project-1", workspace_id="workspace-1",
            fact_type="customer_preference", fact_value="客户 A 要求导出 xlsx",
            risk_level="medium", version_group="team-1:customer_preference:customer-a:export-format",
            confidence=0.9, importance=0.8,
        )
        memory_store.insert_memory_core(old.to_memory_core())
        team_store.insert_memory(old)
        team_store.create_review_schedule(old)

        llm = FakeLLMClient(_extraction_response(fact_value="客户 A 现在接受 csv"))
        _set_arbitrator_hits([{"memory_id": "mem-old", "distance": 0.1}])
        arbitrator = _make_arbitrator([TeamRetentionArbitrationResult(
            action="candidate", target_memory_id="mem-old", reason="potential_conflict",
        )])
        embedding_store = FakeEmbeddingStore()
        handler = TeamRetentionDomainHandler(
            memory_store, team_store, llm_client=llm, arbitrator=arbitrator,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        runtime = DomainRuntime(
            memory_store=memory_store, add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        result = handler.ingest_event(_event("客户 A 现在好像接受 csv，待确认。"), runtime)
        assert memory_store.get_memory("mem-old")["status"] == "active"
        assert memory_store.get_memory(result.memory_ids[0])["status"] == "candidate"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_arbitration_update_supersedes_old() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        old = TeamRetentionMemory(
            retention_id="mem-old", team_id="team-1", project_id="project-1", workspace_id="workspace-1",
            fact_type="customer_preference", fact_value="客户 A 要求导出 xlsx",
            risk_level="medium", version_group="team-1:customer_preference:customer-a:export-format",
            confidence=0.9, importance=0.8,
        )
        memory_store.insert_memory_core(old.to_memory_core())
        team_store.insert_memory(old)
        team_store.create_review_schedule(old)

        llm = FakeLLMClient(_extraction_response(
            fact_value="客户 A 接受 csv，不再要求 xlsx", topic_key="export-format",
        ))
        _set_arbitrator_hits([{"memory_id": "mem-old", "distance": 0.1}])
        arbitrator = _make_arbitrator([TeamRetentionArbitrationResult(
            action="update", target_memory_id="mem-old", reason="explicit_update",
        )])
        embedding_store = FakeEmbeddingStore()
        handler = TeamRetentionDomainHandler(
            memory_store, team_store, llm_client=llm, arbitrator=arbitrator,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        runtime = DomainRuntime(
            memory_store=memory_store, add_memory=memory_store.insert_memory_core,
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


def test_arbitration_strengthen_reinforces() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        old = TeamRetentionMemory(
            retention_id="mem-old", team_id="team-1", project_id="project-1", workspace_id="workspace-1",
            fact_type="customer_preference", fact_value="客户 A 要求导出 xlsx，不接受 csv",
            risk_level="medium", version_group="team-1:customer_preference:customer-a:export-format",
            confidence=0.9, importance=0.8,
        )
        memory_store.insert_memory_core(old.to_memory_core())
        team_store.insert_memory(old)
        team_store.create_review_schedule(old)

        llm = FakeLLMClient(_extraction_response(
            fact_value="客户 A 要求导出用 xlsx，csv 不行", topic_key="export-format",
        ))
        _set_arbitrator_hits([{"memory_id": "mem-old", "distance": 0.05}])
        arbitrator = _make_arbitrator([TeamRetentionArbitrationResult(
            action="strengthen", target_memory_id="mem-old", reason="same_fact_different_wording",
        )])
        embedding_store = FakeEmbeddingStore()
        handler = TeamRetentionDomainHandler(
            memory_store, team_store, llm_client=llm, arbitrator=arbitrator,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        runtime = DomainRuntime(
            memory_store=memory_store, add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        result = handler.ingest_event(_event("客户 A 要求导出用 xlsx，csv 不行。"), runtime)
        assert result.memory_ids == ["mem-old"]
        assert memory_store.get_memory("mem-old")["status"] == "active"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_arbitration_conflict_stores_candidate() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        old = TeamRetentionMemory(
            retention_id="mem-old", team_id="team-1", project_id="project-1", workspace_id="workspace-1",
            fact_type="customer_preference", fact_value="客户 A 要求导出 xlsx",
            risk_level="medium", version_group="team-1:customer_preference:customer-a:export-format",
            confidence=0.9, importance=0.8,
        )
        memory_store.insert_memory_core(old.to_memory_core())
        team_store.insert_memory(old)
        team_store.create_review_schedule(old)

        llm = FakeLLMClient(_extraction_response(
            fact_value="客户 A 要求导出 csv", topic_key="export-format",
        ))
        _set_arbitrator_hits([{"memory_id": "mem-old", "distance": 0.1}])
        arbitrator = _make_arbitrator([TeamRetentionArbitrationResult(
            action="candidate", target_memory_id="mem-old", reason="conflict_same_fact_diff_value",
        )])
        embedding_store = FakeEmbeddingStore()
        handler = TeamRetentionDomainHandler(
            memory_store, team_store, llm_client=llm, arbitrator=arbitrator,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        runtime = DomainRuntime(
            memory_store=memory_store, add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        result = handler.ingest_event(_event("客户 A 要求导出 csv。"), runtime)
        new_id = result.memory_ids[0]
        assert memory_store.get_memory(new_id)["status"] == "candidate"
        assert team_store.get_review_schedule(new_id) is None
        assert team_store.get_review_schedule("mem-old").active is True
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_embedding_metadata_filters_none() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(_extraction_response())
        embedding_store = FakeEmbeddingStore()
        handler = TeamRetentionDomainHandler(
            memory_store, team_store, llm_client=llm,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        runtime = DomainRuntime(
            memory_store=memory_store, add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        event = NormalizedEvent(
            event_id="event-no-scope",
            event_type="chat_message", source_type="feishu_chat",
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


def test_embedding_failure_does_not_break_ingest() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(_extraction_response())
        handler = TeamRetentionDomainHandler(
            memory_store, team_store, llm_client=llm,
            embedding_store=RaisingEmbeddingStore(),  # type: ignore[arg-type]
        )
        runtime = DomainRuntime(
            memory_store=memory_store, add_memory=memory_store.insert_memory_core,
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


def test_active_ingest_card_includes_computed_next_review_time() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        notifier = FakeNotifier()
        llm = FakeLLMClient(_extraction_response(risk_level="high"))
        handler = TeamRetentionDomainHandler(
            memory_store,
            team_store,
            llm_client=llm,
            notifier=notifier,
            chat_id="oc-demo",
        )
        runtime = DomainRuntime(memory_store=memory_store, add_memory=memory_store.insert_memory_core)

        result = handler.ingest_event(_event(), runtime)

        assert len(result.memory_ids) == 1
        assert len(notifier.created_cards) == 1
        _chat_id, suggestion = notifier.created_cards[0]
        schedule = team_store.get_review_schedule(result.memory_ids[0])
        assert schedule is not None
        assert suggestion["due_at"] == schedule.next_review_at
        assert suggestion["due_at"] != "待计算"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_acknowledge_action_is_noop_success_for_created_card() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        handler = TeamRetentionDomainHandler(memory_store, team_store)

        result = handler.update_memory("acknowledge", memory_id="mem-any")

        assert result is not None
        assert result.updated is True
        assert result.message == "acknowledged"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_llm_failure_fallback_to_rule_supersede() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        old_event = _event("请团队长期记住：客户 A 要求所有导出文件使用 xlsx。")
        old_event.payload.update({
            "memory_intent": "team_retention",
            "fact_type": "customer_preference",
            "fact_value": "客户 A 要求导出 xlsx",
            "version_group": "team-1:customer-a-export-format",
        })
        llm = RaisingLLMClient()
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store, add_memory=memory_store.insert_memory_core,
            embedding_store=FakeEmbeddingStore(),  # type: ignore[arg-type]
        )
        first = handler.ingest_event(old_event, runtime)
        new_event = _event("请团队长期记住：客户 A 现在接受 csv，但必须 UTF-8 编码。")
        new_event.payload.update({
            "memory_intent": "team_retention",
            "fact_type": "customer_preference",
            "fact_value": "客户 A 现在接受 csv，但必须 UTF-8 编码",
            "version_group": "team-1:customer-a-export-format",
        })
        second = handler.ingest_event(new_event, runtime)
        assert llm.calls == 2
        assert len(first.memory_ids) == 1
        assert len(second.memory_ids) == 1
        assert first.memory_ids[0] != second.memory_ids[0]
        assert memory_store.get_memory(first.memory_ids[0])["status"] == "superseded"
        assert memory_store.get_memory(second.memory_ids[0])["status"] == "active"
        assert team_store.get_review_schedule(first.memory_ids[0]).active is False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_prompt_does_not_include_raw_secrets() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(_extraction_response())
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store, add_memory=memory_store.insert_memory_core,
            embedding_store=FakeEmbeddingStore(),  # type: ignore[arg-type]
        )
        event = _event("请团队长期记住：api key = sk-secretsecret 已更新。")
        event.payload["api_key"] = "sk-payloadsecret"
        handler.ingest_event(event, runtime)
        prompt = llm.calls[0]["user_prompt"]
        assert "sk-secretsecret" not in prompt
        assert "sk-payloadsecret" not in prompt
        assert "[REDACTED]" in prompt
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_sensitive_policy_prompt_reference() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(_extraction_response())
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store, add_memory=memory_store.insert_memory_core,
            embedding_store=FakeEmbeddingStore(),  # type: ignore[arg-type]
        )
        handler.ingest_event(_event("请团队长期记住：api key = sk-secretsecret 已更新。"), runtime)
        system_prompt = llm.calls[0]["system_prompt"]
        assert "只输出" in system_prompt or "JSON" in system_prompt
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_low_confidence_vague_chat_rejected_or_candidate() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        llm = FakeLLMClient(_extraction_response(
            is_team_retention=True, fact_type="team_fact",
            fact_value="下午必须长期看一下这个问题。",
            certainty="speculative", evidence_quality="implied", fact_specificity="vague",
            risk_level="low", time_sensitivity="stable", scope_impact="individual",
            irreversibility="low_cost",
        ))
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store, add_memory=memory_store.insert_memory_core,
            embedding_store=FakeEmbeddingStore(),  # type: ignore[arg-type]
        )
        result = handler.ingest_event(_event("以后必须长期看一下。"), runtime)
        if result.memory_ids:
            row = memory_store.get_memory(result.memory_ids[0])
            assert row["status"] in {"candidate", "reject"}
        else:
            assert result.candidate_count <= 1
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_legacy_fields_ignored() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        response = _extraction_response(
            certainty="speculative", fact_specificity="vague",
            evidence_quality="implied", risk_level="medium",
        )
        llm = FakeLLMClient(response)
        handler = TeamRetentionDomainHandler(memory_store, team_store, llm_client=llm)
        runtime = DomainRuntime(
            memory_store=memory_store, add_memory=memory_store.insert_memory_core,
            embedding_store=FakeEmbeddingStore(),  # type: ignore[arg-type]
        )
        result = handler.ingest_event(_event("客户 A 可能以后不接受 csv，待确认。"), runtime)
        assert memory_store.get_memory(result.memory_ids[0])["status"] == "candidate"
        assert team_store.get_review_schedule(result.memory_ids[0]) is None
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
