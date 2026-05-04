from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from src.domains.project_decision import ProjectDecision, ProjectDecisionQuery, ProjectDecisionRetriever
from src.storage import MemoryCoreStore


class FakeEmbeddingStore:
    def __init__(self, hits: list[dict[str, object]] | None = None) -> None:
        self.hits = hits or []
        self.queries: list[dict[str, object]] = []

    def query_similar(
        self,
        text: str,
        domain: str | None = None,
        *,
        top_k: int = 10,
        filters: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        self.queries.append({"text": text, "domain": domain, "top_k": top_k, "filters": filters})
        return self.hits


class RaisingEmbeddingStore(FakeEmbeddingStore):
    def query_similar(
        self,
        text: str,
        domain: str | None = None,
        *,
        top_k: int = 10,
        filters: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        raise RuntimeError("vector unavailable")


class FakeEmbeddingClient:
    def __init__(self, vector: list[float]) -> None:
        self.vector = vector
        self.texts: list[str] = []

    def embed_text(self, text: str) -> list[float]:
        self.texts.append(text)
        return self.vector


class FakeVectorEmbeddingStore(FakeEmbeddingStore):
    def query_by_embedding(
        self,
        vector: list[float],
        domain: str | None = None,
        top_k: int = 10,
        filters: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        self.queries.append({"vector": vector, "domain": domain, "top_k": top_k, "filters": filters})
        return self.hits


class VariantEmbeddingStore(FakeEmbeddingStore):
    def __init__(self, hits_by_text: dict[str, list[dict[str, object]]]) -> None:
        super().__init__()
        self.hits_by_text = hits_by_text

    def query_similar(
        self,
        text: str,
        domain: str | None = None,
        *,
        top_k: int = 10,
        filters: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        self.queries.append({"text": text, "domain": domain, "top_k": top_k, "filters": filters})
        if text == "原始表达失败":
            raise RuntimeError("single variant failed")
        return self.hits_by_text.get(text, [])


def _store() -> MemoryCoreStore:
    root = Path.cwd() / ".tmp-tests"
    root.mkdir(exist_ok=True)
    temp_dir = root / f"project-decision-retriever-{uuid.uuid4().hex}"
    temp_dir.mkdir()
    store = MemoryCoreStore(str(temp_dir / "memory.db"))
    store.create_table()
    store._test_temp_dir = temp_dir  # type: ignore[attr-defined]
    return store


def _cleanup(store: MemoryCoreStore) -> None:
    shutil.rmtree(store._test_temp_dir, ignore_errors=True)  # type: ignore[attr-defined]


def _insert(
    store: MemoryCoreStore,
    memory_id: str,
    *,
    project_id: str = "project-1",
    topic: str = "检索层方案",
    decision: str = "采用方案 B",
    stage: str = "技术选型",
    status: str = "confirmed",
) -> None:
    decision = ProjectDecision(
        decision_id=memory_id,
        project_id=project_id,
        topic=topic,
        decision=decision,
        stage=stage,
        status=status,  # type: ignore[arg-type]
        source_ref=f"source-{memory_id}",
        confidence=0.9,
        importance=0.8,
    )
    store.insert_memory_core(decision.to_memory_core())
    if status == "superseded":
        store.update_memory_status(memory_id, "superseded")


def test_retrieve_filters_by_project_id() -> None:
    store = _store()
    try:
        _insert(store, "mem-project-1", project_id="project-1")
        _insert(store, "mem-project-2", project_id="project-2")

        results = ProjectDecisionRetriever(store).retrieve(
            ProjectDecisionQuery(query_text="检索层方案", project_id="project-1")
        )

        assert [result.decision.decision_id for result in results] == ["mem-project-1"]
    finally:
        _cleanup(store)


def test_retrieve_matches_topic_and_stage() -> None:
    store = _store()
    try:
        _insert(store, "mem-target", topic="数据库选型", stage="技术选型")
        _insert(store, "mem-other", topic="上线计划", stage="联调")

        results = ProjectDecisionRetriever(store).retrieve(
            ProjectDecisionQuery(query_text="数据库", topic="数据库选型", stage="技术选型")
        )

        assert len(results) == 1
        assert results[0].decision.decision_id == "mem-target"
        assert "topic" in results[0].matched_fields
        assert "stage" in results[0].matched_fields
    finally:
        _cleanup(store)


def test_retrieve_excludes_superseded_by_default() -> None:
    store = _store()
    try:
        _insert(store, "mem-active")
        _insert(store, "mem-old", status="superseded")

        results = ProjectDecisionRetriever(store).retrieve(
            ProjectDecisionQuery(query_text="检索层方案", include_superseded=False)
        )

        assert {result.decision.decision_id for result in results} == {"mem-active"}
    finally:
        _cleanup(store)


def test_retrieve_cards_applies_min_score() -> None:
    store = _store()
    try:
        _insert(store, "mem-card")

        cards = ProjectDecisionRetriever(store).retrieve_cards(
            ProjectDecisionQuery(query_text="为什么选方案 B", topic="检索层方案", project_id="project-1"),
            min_score=0.55,
        )

        assert len(cards) == 1
        assert cards[0]["type"] == "project_decision_card"
        assert cards[0]["score"] >= 0.55
        assert cards[0]["match_reason"]
    finally:
        _cleanup(store)


def test_retrieve_adds_vector_hits_as_candidates() -> None:
    store = _store()
    try:
        _insert(store, "mem-vector", topic="预算审批", project_id="project-1")

        embedding_store = FakeEmbeddingStore([{"memory_id": "mem-vector", "distance": 0.2}])
        results = ProjectDecisionRetriever(
            store,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        ).retrieve(
            ProjectDecisionQuery(query_text="之前为什么没有用更便宜的采购方案", project_id="project-1"),
            limit=5,
        )

        assert [result.decision.decision_id for result in results] == ["mem-vector"]
        assert "vector_similarity" in results[0].matched_fields
        assert results[0].memory_item.extra["vector_similarity"] == 0.8
        assert embedding_store.queries[0]["domain"] == "project_decision"
        assert embedding_store.queries[0]["filters"] == {"project_id": "project-1"}
    finally:
        _cleanup(store)


def test_retrieve_adds_bm25_score_for_keyword_hit() -> None:
    store = _store()
    try:
        _insert(
            store,
            "mem-bm25",
            topic="SQLite storage",
            decision="Use SQLite for local demo storage",
            project_id="project-1",
        )

        results = ProjectDecisionRetriever(store).retrieve(
            ProjectDecisionQuery(query_text="SQLite storage", project_id="project-1"),
            limit=5,
        )

        assert results[0].decision.decision_id == "mem-bm25"
        assert "bm25" in results[0].matched_fields
        assert results[0].memory_item.extra["bm25_score"] > 0
    finally:
        _cleanup(store)


def test_retrieve_uses_embedding_client_vector_when_available() -> None:
    store = _store()
    try:
        _insert(store, "mem-vector-client", topic="架构选型", project_id="project-1")

        embedding_store = FakeVectorEmbeddingStore([{"memory_id": "mem-vector-client", "distance": 0.1}])
        embedding_client = FakeEmbeddingClient([0.2, 0.8])
        ProjectDecisionRetriever(
            store,
            embedding_store=embedding_store,  # type: ignore[arg-type]
            embedding_client=embedding_client,  # type: ignore[arg-type]
        ).retrieve(ProjectDecisionQuery(query_text="架构选择原因", project_id="project-1"), limit=5)

        assert embedding_client.texts == ["架构选择原因"]
        assert embedding_store.queries[0]["vector"] == [0.2, 0.8]
    finally:
        _cleanup(store)


def test_vector_failure_falls_back_to_rule_retrieval() -> None:
    store = _store()
    try:
        _insert(store, "mem-rule", topic="数据库选型", project_id="project-1")

        results = ProjectDecisionRetriever(
            store,
            embedding_store=RaisingEmbeddingStore(),  # type: ignore[arg-type]
        ).retrieve(ProjectDecisionQuery(query_text="数据库", topic="数据库选型", project_id="project-1"))

        assert [result.decision.decision_id for result in results] == ["mem-rule"]
        assert "topic" in results[0].matched_fields
    finally:
        _cleanup(store)


def test_retrieve_queries_all_query_variants_and_merges_highest_similarity() -> None:
    store = _store()
    try:
        _insert(store, "mem-shared", topic="预算审批", project_id="project-1")
        embedding_store = VariantEmbeddingStore(
            {
                "原始表达": [{"memory_id": "mem-shared", "distance": 0.4}],
                "改写表达": [{"memory_id": "mem-shared", "distance": 0.1}],
            }
        )

        results = ProjectDecisionRetriever(
            store,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        ).retrieve(
            ProjectDecisionQuery(
                query_text="原始表达",
                query_variants=["原始表达", "改写表达"],
                project_id="project-1",
            ),
            limit=5,
        )

        assert [query["text"] for query in embedding_store.queries] == ["原始表达", "改写表达"]
        assert results[0].decision.decision_id == "mem-shared"
        assert results[0].memory_item.extra["vector_similarity"] == 0.9
        assert results[0].memory_item.extra["vector_query"] == "改写表达"
    finally:
        _cleanup(store)


def test_single_query_variant_failure_keeps_other_vector_hits() -> None:
    store = _store()
    try:
        _insert(store, "mem-rewritten", topic="预算审批", project_id="project-1")
        embedding_store = VariantEmbeddingStore(
            {
                "改写表达": [{"memory_id": "mem-rewritten", "distance": 0.2}],
            }
        )

        results = ProjectDecisionRetriever(
            store,
            embedding_store=embedding_store,  # type: ignore[arg-type]
        ).retrieve(
            ProjectDecisionQuery(
                query_text="原始表达失败",
                query_variants=["原始表达失败", "改写表达"],
                project_id="project-1",
            ),
            limit=5,
        )

        assert [query["text"] for query in embedding_store.queries] == ["原始表达失败", "改写表达"]
        assert [result.decision.decision_id for result in results] == ["mem-rewritten"]
        assert results[0].memory_item.extra["vector_similarity"] == 0.8
    finally:
        _cleanup(store)
