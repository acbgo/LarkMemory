from __future__ import annotations

import unittest
from unittest.mock import patch

from src.storage.embedding_store import EmbeddingStore, chromadb


class FakeCollection:
    def __init__(self) -> None:
        self.upsert_calls: list[dict] = []
        self.query_calls: list[dict] = []
        self.delete_calls: list[dict] = []
        self.get_calls: list[dict] = []
        self.query_result = {
            "ids": [["memory-1"]],
            "documents": [["Use SQLite"]],
            "metadatas": [[{"domain": "project_decision", "topic": "db"}]],
            "distances": [[0.12]],
        }
        self.get_result = {
            "ids": ["memory-1"],
            "documents": ["Use SQLite"],
            "metadatas": [{"domain": "project_decision"}],
        }

    def upsert(self, **kwargs: dict) -> None:
        self.upsert_calls.append(kwargs)

    def query(self, **kwargs: dict) -> dict:
        self.query_calls.append(kwargs)
        return self.query_result

    def delete(self, **kwargs: dict) -> None:
        self.delete_calls.append(kwargs)

    def get(self, **kwargs: dict) -> dict:
        self.get_calls.append(kwargs)
        return self.get_result


class FakeClient:
    def __init__(self, collection: FakeCollection) -> None:
        self.collection = collection
        self.get_or_create_calls: list[dict] = []

    def get_or_create_collection(self, **kwargs: dict) -> FakeCollection:
        self.get_or_create_calls.append(kwargs)
        return self.collection


class TestEmbeddingStore(unittest.TestCase):
    def test_create_collection_raises_without_chromadb(self) -> None:
        if chromadb is not None:
            self.skipTest("chromadb is installed in this environment")

        store = EmbeddingStore(
            collection_name="memory_core",
            persist_directory="./tmp_chroma",
        )

        with self.assertRaises(ImportError):
            store.create_collection()

    def test_query_and_upsert_methods_normalize_and_merge_filters(self) -> None:
        collection = FakeCollection()
        store = EmbeddingStore(
            collection_name="memory_core",
            persist_directory="./tmp_chroma",
        )
        store._collection = collection

        store.upsert_embedding(
            memory_id="memory-1",
            text="Use SQLite",
            metadata={"domain": "project_decision"},
            embedding=[0.1, 0.2],
        )
        store.upsert_many(
            [
                {
                    "memory_id": "memory-2",
                    "text": "Use PostgreSQL",
                    "metadata": {"domain": "project_decision"},
                    "embedding": [0.3, 0.4],
                }
            ]
        )
        rows = store.query_similar(
            "database choice",
            domain="project_decision",
            filters={"status": "active"},
        )
        by_embedding_rows = store.query_by_embedding(
            [0.9, 0.8],
            domain="project_decision",
            filters={"status": "active"},
        )

        self.assertEqual(collection.upsert_calls[0]["ids"], ["memory-1"])
        self.assertEqual(collection.upsert_calls[1]["ids"], ["memory-2"])
        self.assertEqual(
            collection.query_calls[0]["where"],
            {"$and": [{"status": "active"}, {"domain": "project_decision"}]},
        )
        self.assertEqual(rows[0]["memory_id"], "memory-1")
        self.assertEqual(rows[0]["document"], "Use SQLite")
        self.assertEqual(rows[0]["distance"], 0.12)
        self.assertEqual(by_embedding_rows[0]["id"], "memory-1")

    def test_build_where_uses_plain_filter_for_single_condition_and_and_for_many(self) -> None:
        store = EmbeddingStore(
            collection_name="memory_core",
            persist_directory="./tmp_chroma",
        )

        self.assertIsNone(store._build_where(None, None))
        self.assertEqual(store._build_where("project_decision", None), {"domain": "project_decision"})
        self.assertEqual(
            store._build_where(
                "project_decision",
                {"project_id": "project-1", "team_id": "team-1"},
            ),
            {
                "$and": [
                    {"project_id": "project-1"},
                    {"team_id": "team-1"},
                    {"domain": "project_decision"},
                ]
            },
        )

    def test_create_collection_disables_chroma_default_embedding_function(self) -> None:
        collection = FakeCollection()
        fake_client = FakeClient(collection)
        store = EmbeddingStore(
            collection_name="memory_core",
            persist_directory="./tmp_chroma",
        )

        with patch("src.storage.embedding_store.chromadb") as fake_chromadb:
            fake_chromadb.PersistentClient.return_value = fake_client
            store.create_collection()

        self.assertEqual(
            fake_client.get_or_create_calls[0],
            {"name": "memory_core", "embedding_function": None},
        )
        self.assertIs(store._collection, collection)

    def test_get_meta_delete_by_domain_and_rebuild_index(self) -> None:
        collection = FakeCollection()
        store = EmbeddingStore(
            collection_name="memory_core",
            persist_directory="./tmp_chroma",
        )
        store._collection = collection

        meta = store.get_embedding_meta("memory-1")
        deleted = store.delete_by_domain("project_decision")
        store.rebuild_index(
            [
                {
                    "memory_id": "memory-3",
                    "text": "Use MySQL",
                    "metadata": {"domain": "project_decision"},
                }
            ]
        )

        self.assertEqual(meta["memory_id"], "memory-1")
        self.assertEqual(collection.get_calls[0]["ids"], ["memory-1"])
        self.assertEqual(collection.get_calls[1]["where"], {"domain": "project_decision"})
        self.assertEqual(deleted, 1)
        self.assertEqual(collection.delete_calls[0]["ids"], ["memory-1"])
        self.assertEqual(collection.delete_calls[1]["ids"], ["memory-1"])
        self.assertEqual(collection.upsert_calls[0]["ids"], ["memory-3"])
