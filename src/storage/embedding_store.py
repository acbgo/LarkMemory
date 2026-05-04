from __future__ import annotations

import logging
from typing import Any

try:
    import chromadb
except ImportError:
    chromadb = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


class EmbeddingStore:
    def __init__(self, collection_name: str, persist_directory: str) -> None:
        """初始化向量存储配置，输入 collection 名称和持久化目录。"""
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        self._client = None
        self._collection = None

    def create_collection(self, name: str | None = None) -> None:
        """创建或获取 Chroma collection，输入可选新名称并更新当前 collection。"""
        if chromadb is None:
            raise ImportError("Missing dependency: chromadb")
        if name is not None:
            self.collection_name = name
        self._client = chromadb.PersistentClient(path=self.persist_directory)
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=None,
        )
        logger.info(
            "action=embedding_collection_ready collection=%s persist_directory=%s",
            self.collection_name,
            self.persist_directory,
        )

    def upsert_embedding(
        self,
        memory_id: str,
        text: str,
        metadata: dict[str, Any],
        embedding: list[float] | None = None,
    ) -> None:
        """按 memory_id 写入单条文本、metadata 和可选 embedding。"""
        collection = self._require_collection()
        payload: dict[str, Any] = {
            "ids": [memory_id],
            "documents": [text],
            "metadatas": [metadata],
        }
        if embedding is not None:
            payload["embeddings"] = [embedding]
        collection.upsert(**payload)
        logger.info(
            "action=embedding_upserted memory_id=%s has_embedding=%s",
            memory_id,
            embedding is not None,
        )

    def upsert_many(self, items: list[dict[str, Any]]) -> None:
        """批量写入 embedding 条目，输入包含 memory_id、text、metadata 的字典列表。"""
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
        logger.info(
            "action=embedding_batch_upserted item_count=%s has_any_embedding=%s",
            len(items),
            "embeddings" in payload,
        )

    def query_similar(
        self,
        text: str,
        domain: str | None = None,
        *,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """按查询文本检索相似向量，返回标准化命中列表。"""
        collection = self._require_collection()
        result = collection.query(
            query_texts=[text],
            n_results=top_k,
            where=self._build_where(domain, filters),
        )
        rows = self._normalize_query_result(result)
        logger.info(
            "action=embedding_text_query_done domain=%s top_k=%s result_count=%s",
            domain,
            top_k,
            len(rows),
        )
        return rows

    def query_by_embedding(
        self,
        vector: list[float],
        domain: str | None = None,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """按查询向量检索相似条目，返回标准化命中列表。"""
        collection = self._require_collection()
        result = collection.query(
            query_embeddings=[vector],
            n_results=top_k,
            where=self._build_where(domain, filters),
        )
        rows = self._normalize_query_result(result)
        logger.info(
            "action=embedding_vector_query_done domain=%s top_k=%s result_count=%s",
            domain,
            top_k,
            len(rows),
        )
        return rows

    def get_embedding_meta(self, memory_id: str) -> dict[str, Any] | None:
        """按 memory_id 查询向量元数据，返回文本、metadata 和 ID 信息。"""
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
        """按 memory_id 删除单条向量记录。"""
        collection = self._require_collection()
        collection.delete(ids=[memory_id])
        logger.info("action=embedding_deleted memory_id=%s", memory_id)

    def delete_by_domain(self, domain: str) -> int:
        """删除指定 domain 下的向量记录，返回删除数量。"""
        collection = self._require_collection()
        result = collection.get(where={"domain": domain}, include=[])
        ids = result.get("ids", [])
        if not ids:
            return 0
        collection.delete(ids=ids)
        logger.info("action=embedding_domain_deleted domain=%s count=%s", domain, len(ids))
        return len(ids)

    def rebuild_index(self, items: list[dict[str, Any]]) -> None:
        """用给定条目重建当前 collection 的索引内容。"""
        collection = self._require_collection()
        existing = collection.get(include=[])
        existing_ids = existing.get("ids", [])
        if existing_ids:
            collection.delete(ids=existing_ids)
        self.upsert_many(items)
        logger.info(
            "action=embedding_index_rebuilt old_count=%s new_count=%s",
            len(existing_ids),
            len(items),
        )

    def _require_collection(self) -> Any:
        """返回当前 collection；未创建时先按配置创建。"""
        if self._collection is None:
            self.create_collection()
        return self._collection

    def _build_where(
        self,
        domain: str | None,
        filters: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """合并 domain 与外部 filters，返回 Chroma where 条件。"""
        where: dict[str, Any] = {}
        if filters:
            where.update(filters)
        if domain is not None:
            where["domain"] = domain
        if not where:
            logger.debug("action=embedding_where_built condition_count=0")
            return None
        if len(where) == 1:
            logger.debug("action=embedding_where_built condition_count=1")
            return where
        logger.debug("action=embedding_where_built condition_count=%s", len(where))
        return {"$and": [{key: value} for key, value in where.items()]}

    def _normalize_query_result(self, result: dict[str, Any]) -> list[dict[str, Any]]:
        """将 Chroma query 结果规范化为统一的命中字典列表。"""
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
