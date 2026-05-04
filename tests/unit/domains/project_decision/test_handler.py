from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from src.core.domain_handler import DomainRuntime
from src.domains.project_decision import ProjectDecisionDomainHandler
from src.schemas import EventContext, NormalizedEvent
from src.storage import MemoryCoreStore


class FakeEmbeddingStore:
    def __init__(self) -> None:
        self.upserts: list[dict[str, Any]] = []

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


class RaisingEmbeddingStore(FakeEmbeddingStore):
    def upsert_embedding(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("embedding store down")


class FakeEmbeddingClient:
    def embed_text(self, text: str) -> list[float]:
        return [0.1, 0.9]


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
