from __future__ import annotations

from typing import Any

try:
    import chromadb
except ImportError:
    chromadb = None  # type: ignore[assignment]


class EmbeddingStore:
    def __init__(self, collection_name: str, persist_directory: str) -> None:
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        self._client = None
        self._collection = None

    def create_collection(self, name: str | None = None) -> None:
        if chromadb is None:
            raise ImportError("Missing dependency: chromadb")
        if name is not None:
            self.collection_name = name
        self._client = chromadb.PersistentClient(path=self.persist_directory)
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name
        )

    def upsert_embedding(
        self,
        memory_id: str,
        text: str,
        metadata: dict[str, Any],
        embedding: list[float] | None = None,
    ) -> None:
        collection = self._require_collection()
        payload: dict[str, Any] = {
            "ids": [memory_id],
            "documents": [text],
            "metadatas": [metadata],
        }
        if embedding is not None:
            payload["embeddings"] = [embedding]
        collection.upsert(**payload)

    def upsert_many(self, items: list[dict[str, Any]]) -> None:
        if not items:
            return
        collection = self._require_collection()
        payload: dict[str, Any] = {
            "ids": [item["memory_id"] for item in items],
            "documents": [item["text"] for item in items],
            "metadatas": [item["metadata"] for item in items],
        }
        if any(item.get("embedding") is not None for item in items):
            payload["embeddings"] = [item.get("embedding") for item in items]
        collection.upsert(**payload)

    def query_similar(
        self,
        text: str,
        domain: str | None = None,
        *,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        collection = self._require_collection()
        result = collection.query(
            query_texts=[text],
            n_results=top_k,
            where=self._build_where(domain, filters),
        )
        return self._normalize_query_result(result)

    def query_by_embedding(
        self,
        vector: list[float],
        domain: str | None = None,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        collection = self._require_collection()
        result = collection.query(
            query_embeddings=[vector],
            n_results=top_k,
            where=self._build_where(domain, filters),
        )
        return self._normalize_query_result(result)

    def get_embedding_meta(self, memory_id: str) -> dict[str, Any] | None:
        collection = self._require_collection()
        result = collection.get(ids=[memory_id], include=["documents", "metadatas"])
        ids = result.get("ids", [])
        if not ids:
            return None
        documents = result.get("documents", [])
        metadatas = result.get("metadatas", [])
        return {
            "memory_id": ids[0],
            "id": ids[0],
            "text": documents[0] if documents else None,
            "document": documents[0] if documents else None,
            "metadata": metadatas[0] if metadatas else None,
        }

    def delete_embedding(self, memory_id: str) -> None:
        collection = self._require_collection()
        collection.delete(ids=[memory_id])

    def delete_by_domain(self, domain: str) -> int:
        collection = self._require_collection()
        result = collection.get(where={"domain": domain}, include=[])
        ids = result.get("ids", [])
        if not ids:
            return 0
        collection.delete(ids=ids)
        return len(ids)

    def rebuild_index(self, items: list[dict[str, Any]]) -> None:
        collection = self._require_collection()
        existing = collection.get(include=[])
        existing_ids = existing.get("ids", [])
        if existing_ids:
            collection.delete(ids=existing_ids)
        self.upsert_many(items)

    def _require_collection(self) -> Any:
        if self._collection is None:
            self.create_collection()
        return self._collection

    def _build_where(
        self,
        domain: str | None,
        filters: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        where: dict[str, Any] = {}
        if filters:
            where.update(filters)
        if domain is not None:
            where["domain"] = domain
        return where or None

    def _normalize_query_result(self, result: dict[str, Any]) -> list[dict[str, Any]]:
        ids = result.get("ids", [])
        documents = result.get("documents", [])
        metadatas = result.get("metadatas", [])
        distances = result.get("distances", [])

        if ids and isinstance(ids[0], list):
            ids = ids[0]
        if documents and isinstance(documents[0], list):
            documents = documents[0]
        if metadatas and isinstance(metadatas[0], list):
            metadatas = metadatas[0]
        if distances and isinstance(distances[0], list):
            distances = distances[0]

        hits: list[dict[str, Any]] = []
        for index, memory_id in enumerate(ids):
            document = documents[index] if index < len(documents) else None
            metadata = metadatas[index] if index < len(metadatas) else None
            distance = distances[index] if index < len(distances) else None
            hits.append(
                {
                    "memory_id": memory_id,
                    "id": memory_id,
                    "text": document,
                    "document": document,
                    "metadata": metadata,
                    "distance": distance,
                }
            )
        return hits
