from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from src.core.domain_handler import DomainRuntime
from src.domains.project_decision import ProjectDecisionDomainHandler
from src.domains.project_decision.models import ProjectDecision, ProjectDecisionCandidate
from src.schemas import EventContext, NormalizedEvent
from src.storage import MemoryCoreStore


class FakeEmbeddingStore:
    def __init__(self) -> None:
        self.upserts: list[dict[str, Any]] = []
        self.query_hits: list[dict[str, Any]] = []

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

    def query_by_embedding(
        self,
        vector: list[float],
        *,
        domain: str | None = None,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return list(self.query_hits[:top_k])

    def query_similar(
        self,
        text: str,
        domain: str | None = None,
        *,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return list(self.query_hits[:top_k])


class RaisingEmbeddingStore(FakeEmbeddingStore):
    def upsert_embedding(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("embedding store down")


class RaisingQueryEmbeddingStore(FakeEmbeddingStore):
    def query_similar(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        raise RuntimeError("semantic query down")


class FakeEmbeddingClient:
    def embed_text(self, text: str) -> list[float]:
        return [0.1, 0.9]


class FakeDecisionJudgeLLM:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = list(payloads)

    async def ajson(self, system_prompt: str | None, user_prompt: str, **kwargs: Any) -> dict[str, Any]:
        if not self.payloads:
            raise AssertionError("unexpected LLM call")
        return self.payloads.pop(0)


class StaticExtractor:
    def __init__(self, decisions: list[ProjectDecision]) -> None:
        self.decisions = list(decisions)
        self.index = 0

    def extract(self, event: NormalizedEvent) -> list[ProjectDecisionCandidate]:
        if self.index >= len(self.decisions):
            raise AssertionError("unexpected extract call")
        decision = self.decisions[self.index]
        self.index += 1
        return [ProjectDecisionCandidate(decision=decision, evidence_text=event.content_text)]


def _store() -> tuple[MemoryCoreStore, Path]:
    root = Path.cwd() / ".tmp-tests"
    root.mkdir(exist_ok=True)
    temp_dir = root / f"project-decision-handler-{uuid.uuid4().hex}"
    temp_dir.mkdir()
    store = MemoryCoreStore(str(temp_dir / "memory.db"))
    store.create_table()
    return store, temp_dir


def _event(content_text: str = "我们决定采用方案 B，因为接入成本更低") -> NormalizedEvent:
    return NormalizedEvent(
        event_id=f"event-{uuid.uuid4().hex}",
        event_type="chat_message",
        source_type="feishu_chat",
        occurred_at="2026-05-04T00:00:00Z",
        context=EventContext(
            project_id="project-1",
            team_id="team-1",
            workspace_id="workspace-1",
            thread_id="thread-1",
        ),
        content_text=content_text,
    )


def _decision_for_event(event: NormalizedEvent, *, decision_id: str, decision_text: str) -> ProjectDecision:
    return ProjectDecision(
        decision_id=decision_id,
        project_id=event.context.project_id,
        workspace_id=event.context.workspace_id,
        team_id=event.context.team_id,
        thread_id=event.context.thread_id,
        topic="方案选型",
        decision=decision_text,
        conclusion=decision_text,
        stage="技术选型",
        source_event_id=event.event_id,
        source_ref=event.context.thread_id,
        confidence=0.9,
        importance=0.8,
    )


def test_ingest_indexes_new_project_decision_memory() -> None:
    memory_store, temp_dir = _store()
    try:
        embedding_store = FakeEmbeddingStore()
        handler = ProjectDecisionDomainHandler(memory_store)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )

        result = handler.ingest_event(_event(), runtime)

        assert len(result.memory_ids) == 1
        assert len(embedding_store.upserts) == 1
        upsert = embedding_store.upserts[0]
        assert upsert["memory_id"] == result.memory_ids[0]
        assert upsert["metadata"]["domain"] == "project_decision"
        assert upsert["metadata"]["status"] == "active"
        assert upsert["metadata"]["project_id"] == "project-1"
        assert "采用方案 B" in upsert["text"]
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_handler_wires_embedding_dependencies_to_default_retriever() -> None:
    memory_store, temp_dir = _store()
    try:
        embedding_store = FakeEmbeddingStore()
        embedding_client = FakeEmbeddingClient()

        handler = ProjectDecisionDomainHandler(
            memory_store,
            embedding_store=embedding_store,  # type: ignore[arg-type]
            embedding_client=embedding_client,  # type: ignore[arg-type]
        )

        assert handler.retriever.embedding_store is embedding_store
        assert handler.retriever.embedding_client is embedding_client
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_duplicate_memory_id_does_not_index_new_candidate() -> None:
    memory_store, temp_dir = _store()
    try:
        embedding_store = FakeEmbeddingStore()
        handler = ProjectDecisionDomainHandler(memory_store)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=lambda _memory: "existing-memory",
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )

        result = handler.ingest_event(_event(), runtime)

        assert result.memory_ids == ["existing-memory"]
        assert embedding_store.upserts == []
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_same_decision_duplicate_reuses_existing_memory_without_supersede() -> None:
    memory_store, temp_dir = _store()
    try:
        handler = ProjectDecisionDomainHandler(memory_store)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
        )

        first = handler.ingest_event(_event("我们决定采用方案 B，因为接入成本更低"), runtime)
        second = handler.ingest_event(_event("再次确认采用方案 B，因为接入成本更低"), runtime)

        assert len(first.memory_ids) == 1
        assert second.memory_ids == first.memory_ids
        assert len(memory_store.list_active_memories(domain="project_decision")) == 1
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_duplicate_reuse_emits_observable_log() -> None:
    memory_store, temp_dir = _store()
    try:
        handler = ProjectDecisionDomainHandler(memory_store)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
        )

        handler.ingest_event(_event("我们决定采用方案 B，因为接入成本更低"), runtime)
        with __import__("unittest").TestCase().assertLogs("src.domains.project_decision.handler", level="INFO") as captured:
            handler.ingest_event(_event("再次确认采用方案 B，因为接入成本更低"), runtime)

        logs = "\n".join(captured.output)
        assert "action=duplicate_detected" in logs
        assert "dedup_action=duplicate" in logs
        assert "matched_memory_id=" in logs
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_changed_decision_supersedes_old_memory_in_same_scope() -> None:
    memory_store, temp_dir = _store()
    try:
        handler = ProjectDecisionDomainHandler(memory_store)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
        )

        first = handler.ingest_event(_event("我们决定采用方案 B，因为接入成本更低"), runtime)
        second = handler.ingest_event(_event("我们决定改为采用方案 C，因为交付风险更低"), runtime)

        assert len(first.memory_ids) == 1
        assert len(second.memory_ids) == 1
        old_row = memory_store.get_memory(first.memory_ids[0])
        new_row = memory_store.get_memory(second.memory_ids[0])
        assert old_row is not None
        assert new_row is not None
        assert old_row["status"] == "superseded"
        assert old_row["superseded_by"] == second.memory_ids[0]
        assert new_row["overwrite_of"] == first.memory_ids[0]
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_semantic_candidates_loaded_are_logged() -> None:
    memory_store, temp_dir = _store()
    try:
        embedding_store = FakeEmbeddingStore()
        handler = ProjectDecisionDomainHandler(
            memory_store,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )

        first = handler.ingest_event(_event("我们决定采用方案 B，因为接入成本更低"), runtime)
        embedding_store.query_hits = [{"memory_id": first.memory_ids[0], "distance": 0.03}]

        with __import__("unittest").TestCase().assertLogs("src.domains.project_decision.handler", level="INFO") as captured:
            handler.ingest_event(_event("再次确认采用方案 B，因为接入成本更低"), runtime)

        logs = "\n".join(captured.output)
        assert "action=semantic_candidates_loaded" in logs
        assert "candidate_count=1" in logs
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_semantic_candidate_failure_falls_back_to_rule_scan() -> None:
    memory_store, temp_dir = _store()
    try:
        embedding_store = RaisingQueryEmbeddingStore()
        handler = ProjectDecisionDomainHandler(
            memory_store,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )

        first = handler.ingest_event(_event("我们决定采用方案 B，因为接入成本更低"), runtime)
        with __import__("unittest").TestCase().assertLogs("src.domains.project_decision.handler", level="WARNING") as captured:
            second = handler.ingest_event(_event("再次确认采用方案 B，因为接入成本更低"), runtime)

        logs = "\n".join(captured.output)
        assert "action=semantic_candidates_failed" in logs
        assert second.memory_ids == first.memory_ids
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_llm_duplicate_judge_reuses_existing_memory_for_semantic_duplicate() -> None:
    memory_store, temp_dir = _store()
    try:
        first_event = _event("我们决定采用方案 B，而不是方案 A，因为接入成本更低")
        second_event = _event("我们决定采用方案 B，而非方案 A，因为接入成本更低")
        handler = ProjectDecisionDomainHandler(
            memory_store,
            llm_client=FakeDecisionJudgeLLM(
                [
                    {
                        "label": "duplicate",
                        "confidence": 0.95,
                        "reason": "结论一致，只是措辞不同",
                    }
                ]
            ),
            extractor=StaticExtractor(
                [
                    _decision_for_event(
                        first_event,
                        decision_id="mem-first",
                        decision_text="采用方案 B，而不是方案 A，因为接入成本更低",
                    ),
                    _decision_for_event(
                        second_event,
                        decision_id="mem-second",
                        decision_text="决定采用方案 B，而非方案 A，因为接入成本更低",
                    ),
                ]
            ),
        )
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
        )

        first = handler.ingest_event(first_event, runtime)
        second = handler.ingest_event(second_event, runtime)

        assert second.memory_ids == first.memory_ids
        assert len(memory_store.list_active_memories(domain="project_decision")) == 1
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_llm_duplicate_judge_reuses_existing_memory_even_when_topic_differs() -> None:
    memory_store, temp_dir = _store()
    try:
        first_event = _event("我们决定采用方案 B，而不是方案 A，因为接入成本更低")
        second_event = _event("我们决定采用方案 B，而非方案 A，因为接入成本更低")
        embedding_store = FakeEmbeddingStore()
        handler = ProjectDecisionDomainHandler(
            memory_store,
            embedding_store=embedding_store,  # type: ignore[arg-type]
            llm_client=FakeDecisionJudgeLLM(
                [
                    {
                        "label": "duplicate",
                        "confidence": 0.95,
                        "reason": "topic 不同，但结论重复",
                    }
                ]
            ),
            extractor=StaticExtractor(
                [
                    _decision_for_event(
                        first_event,
                        decision_id="mem-first-topic-diff",
                        decision_text="采用方案 B，而不是方案 A，因为接入成本更低",
                    ),
                    ProjectDecision(
                        decision_id="mem-second-topic-diff",
                        project_id=second_event.context.project_id,
                        workspace_id=second_event.context.workspace_id,
                        team_id=second_event.context.team_id,
                        thread_id=second_event.context.thread_id,
                        topic="技术路线讨论",
                        decision="决定采用方案 B，而非方案 A，因为接入成本更低",
                        conclusion="决定采用方案 B，而非方案 A，因为接入成本更低",
                        stage="技术选型",
                        source_event_id=second_event.event_id,
                        source_ref=second_event.context.thread_id,
                        confidence=0.9,
                        importance=0.8,
                    ),
                ]
            ),
        )
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        )

        first = handler.ingest_event(first_event, runtime)
        embedding_store.query_hits = [{"memory_id": first.memory_ids[0], "distance": 0.03}]
        second = handler.ingest_event(second_event, runtime)

        assert second.memory_ids == first.memory_ids
        assert len(memory_store.list_active_memories(domain="project_decision")) == 1
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_embedding_index_failure_does_not_break_project_decision_ingest() -> None:
    memory_store, temp_dir = _store()
    try:
        handler = ProjectDecisionDomainHandler(memory_store)
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=memory_store.insert_memory_core,
            embedding_store=RaisingEmbeddingStore(),  # type: ignore[arg-type]
        )

        result = handler.ingest_event(_event(), runtime)

        assert len(result.memory_ids) == 1
        assert memory_store.get_memory(result.memory_ids[0]) is not None
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
