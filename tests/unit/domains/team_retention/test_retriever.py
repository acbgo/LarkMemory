from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from src.domains.team_retention.models import TeamRetentionMemory
from src.domains.team_retention.retriever import TeamRetentionQuery, TeamRetentionRetriever
from src.storage import MemoryCoreStore, TeamRetentionStore


class FakeEmbeddingStore:
    def __init__(self, hits: list[dict[str, object]]) -> None:
        self.hits = hits
        self.queries: list[dict[str, object]] = []

    def query_similar(
        self,
        text: str,
        domain: str | None = None,
        *,
        top_k: int = 10,
        filters: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        self.queries.append(
            {
                "text": text,
                "domain": domain,
                "top_k": top_k,
                "filters": filters,
            }
        )
        return list(self.hits)


def _stores() -> tuple[MemoryCoreStore, TeamRetentionStore, Path]:
    root = Path.cwd() / ".tmp-tests"
    root.mkdir(exist_ok=True)
    temp_dir = root / f"team-retention-retriever-{uuid.uuid4().hex}"
    temp_dir.mkdir()
    db_path = str(temp_dir / "memory.db")
    memory_store = MemoryCoreStore(db_path)
    memory_store.create_table()
    team_store = TeamRetentionStore(db_path)
    team_store.create_table()
    return memory_store, team_store, temp_dir


def _insert(
    memory_store: MemoryCoreStore,
    team_store: TeamRetentionStore,
    memory_id: str,
    *,
    team_id: str = "team-1",
    fact_value: str = "客户 A 要求导出 xlsx",
    status: str = "active",
) -> None:
    memory = TeamRetentionMemory(
        retention_id=memory_id,
        team_id=team_id,
        project_id="project-1",
        fact_type="customer_preference",
        fact_value=fact_value,
        risk_level="medium",
        confidence=0.9,
        importance=0.8,
    )
    core = memory.to_memory_core()
    core.status = status  # type: ignore[assignment]
    memory_store.insert_memory_core(core)
    team_store.insert_memory(memory)
    if status == "candidate":
        team_store.update_memory_metadata(memory_id, {"needs_confirmation": True})


def test_retrieve_filters_by_team_id_and_query_text() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        _insert(memory_store, team_store, "mem-team-1", team_id="team-1")
        _insert(memory_store, team_store, "mem-team-2", team_id="team-2")

        results = TeamRetentionRetriever(memory_store, team_store).retrieve(
            TeamRetentionQuery(query_text="客户 A xlsx", team_id="team-1")
        )

        assert [result.memory.retention_id for result in results] == ["mem-team-1"]
        assert "query_text" in results[0].matched_fields
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_retrieve_requires_scope_to_avoid_cross_team_leakage() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        _insert(memory_store, team_store, "mem-team-1", team_id="team-1")

        results = TeamRetentionRetriever(memory_store, team_store).retrieve(
            TeamRetentionQuery(query_text="客户 A xlsx")
        )

        assert results == []
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_retrieve_includes_candidate_memories_with_status_marker() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        _insert(memory_store, team_store, "mem-candidate", status="candidate")

        results = TeamRetentionRetriever(memory_store, team_store).retrieve(
            TeamRetentionQuery(query_text="客户 A xlsx", team_id="team-1")
        )

        assert [result.memory.retention_id for result in results] == ["mem-candidate"]
        ranked = results[0].to_ranked_memory(rank=1)
        assert ranked.item.extra["status"] == "candidate"
        assert ranked.item.extra["needs_confirmation"] is True
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_retrieve_uses_vector_hits_for_hybrid_recall() -> None:
    memory_store, team_store, temp_dir = _stores()
    try:
        _insert(
            memory_store,
            team_store,
            "mem-vector",
            fact_value="客户 A 要求导出 xlsx",
        )
        embedding_store = FakeEmbeddingStore(
            [
                {
                    "memory_id": "mem-vector",
                    "distance": 0.12,
                    "metadata": {"status": "active", "team_id": "team-1"},
                }
            ]
        )

        results = TeamRetentionRetriever(
            memory_store,
            team_store,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        ).retrieve(
            TeamRetentionQuery(query_text="A 客户的文件格式规则", team_id="team-1")
        )

        assert embedding_store.queries
        assert embedding_store.queries[0]["domain"] == "team_retention"
        assert embedding_store.queries[0]["filters"] == {"team_id": "team-1"}
        assert [result.memory.retention_id for result in results] == ["mem-vector"]
        assert "vector_similarity" in results[0].matched_fields
        assert results[0].memory_item.extra["vector_similarity"] == 0.88
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
