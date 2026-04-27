from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from src.domains.team_retention.models import TeamRetentionMemory
from src.domains.team_retention.retriever import TeamRetentionQuery, TeamRetentionRetriever
from src.storage import MemoryCoreStore, TeamRetentionStore


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
    memory_store.insert_memory_core(memory.to_memory_core())
    team_store.insert_memory(memory)


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
