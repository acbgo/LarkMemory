from __future__ import annotations

from typing import Any

from src.domains.team_retention.embedding import TeamRetentionEmbeddingIndexer
from src.domains.team_retention.models import TeamRetentionMemory


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


class FakeEmbeddingClient:
    def embed_text(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class RaisingEmbeddingClient:
    def embed_text(self, text: str) -> list[float]:
        raise RuntimeError("embedding model down")


def _memory() -> TeamRetentionMemory:
    return TeamRetentionMemory(
        retention_id="team-memory-1",
        team_id="team-1",
        project_id="project-1",
        workspace_id="workspace-1",
        fact_type="team_fact",
        fact_value="客户 A 要求导出文件必须使用 xlsx",
        risk_level="medium",
        version_group="customer-a-export-format",
    )


def test_upsert_uses_embedding_client_vector() -> None:
    store = FakeEmbeddingStore()
    indexer = TeamRetentionEmbeddingIndexer(store, FakeEmbeddingClient())  # type: ignore[arg-type]

    indexer.upsert(_memory(), status="active")

    assert len(store.upserts) == 1
    assert store.upserts[0]["memory_id"] == "team-memory-1"
    assert store.upserts[0]["embedding"] == [0.1, 0.2, 0.3]
    assert store.upserts[0]["metadata"]["domain"] == "team_retention"


def test_upsert_skips_store_when_embedding_client_fails() -> None:
    store = FakeEmbeddingStore()
    indexer = TeamRetentionEmbeddingIndexer(store, RaisingEmbeddingClient())  # type: ignore[arg-type]

    indexer.upsert(_memory(), status="active")

    assert store.upserts == []
