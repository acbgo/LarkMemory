from __future__ import annotations

from typing import Any

from src.domains.project_decision import ProjectDecision, ProjectDecisionEmbeddingIndexer


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
    def __init__(self, vector: list[float] | None = None) -> None:
        self.vector = vector or [0.1, 0.2, 0.3]
        self.calls: list[str] = []

    def embed_text(self, text: str) -> list[float]:
        self.calls.append(text)
        return self.vector


class RaisingEmbeddingClient:
    def embed_text(self, text: str) -> list[float]:
        raise RuntimeError("embedding model down")


def _decision() -> ProjectDecision:
    return ProjectDecision(
        decision_id="decision-1",
        project_id="project-1",
        team_id="team-1",
        workspace_id="workspace-1",
        topic="数据库选型",
        decision="采用 SQLite 作为本地 demo 存储",
        conclusion="先用 SQLite，后续再评估 PostgreSQL",
        reasons=["部署简单", "本地开发成本低"],
        objections=["并发能力有限"],
        alternatives=["PostgreSQL", "SQLite"],
        stage="技术选型",
        source_ref="message-1",
    )


def test_build_text_contains_decision_semantic_fields() -> None:
    text = ProjectDecisionEmbeddingIndexer(None).build_text(_decision())

    assert "主题: 数据库选型" in text
    assert "结论: 采用 SQLite" in text
    assert "理由: 部署简单；本地开发成本低" in text
    assert "反对意见: 并发能力有限" in text
    assert "备选方案: PostgreSQL；SQLite" in text
    assert "project=project-1" in text


def test_build_metadata_filters_none_values() -> None:
    decision = ProjectDecision(
        decision_id="decision-1",
        project_id="project-1",
        topic="数据库选型",
        decision="采用 SQLite",
    )

    metadata = ProjectDecisionEmbeddingIndexer(None).build_metadata(decision, status="active")

    assert metadata["memory_id"] == "decision-1"
    assert metadata["domain"] == "project_decision"
    assert metadata["status"] == "active"
    assert metadata["project_id"] == "project-1"
    assert metadata["topic"] == "数据库选型"
    assert "team_id" not in metadata
    assert "workspace_id" not in metadata
    assert all(value is not None for value in metadata.values())


def test_upsert_uses_embedding_client_vector() -> None:
    store = FakeEmbeddingStore()
    client = FakeEmbeddingClient([0.4, 0.5])
    indexer = ProjectDecisionEmbeddingIndexer(store, client)  # type: ignore[arg-type]

    indexer.upsert(_decision(), status="active")

    assert len(client.calls) == 1
    assert len(store.upserts) == 1
    assert store.upserts[0]["memory_id"] == "decision-1"
    assert store.upserts[0]["embedding"] == [0.4, 0.5]
    assert store.upserts[0]["metadata"]["domain"] == "project_decision"


def test_upsert_continues_without_vector_when_embedding_client_fails() -> None:
    store = FakeEmbeddingStore()
    indexer = ProjectDecisionEmbeddingIndexer(store, RaisingEmbeddingClient())  # type: ignore[arg-type]

    indexer.upsert(_decision(), status="active")

    assert len(store.upserts) == 1
    assert store.upserts[0]["embedding"] is None


def test_upsert_store_failure_does_not_raise() -> None:
    indexer = ProjectDecisionEmbeddingIndexer(RaisingEmbeddingStore())  # type: ignore[arg-type]

    indexer.upsert(_decision(), status="active")
