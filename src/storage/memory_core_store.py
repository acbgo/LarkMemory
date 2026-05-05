from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.schemas import MemoryCore
from src.utils.text import clean_text

from .base import SQLiteStore


logger = logging.getLogger(__name__)


class MemoryCoreStore(SQLiteStore):
    def create_table(self) -> None:
        """创建 MemoryCore 存储表和常用索引。"""
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_core (
                memory_id TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                scope TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_ref TEXT NOT NULL,
                source_event_id TEXT,
                content_text TEXT NOT NULL,
                summary_text TEXT,
                entities_json TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                importance REAL NOT NULL,
                confidence REAL NOT NULL,
                freshness_score REAL,
                status TEXT NOT NULL,
                valid_from TEXT,
                valid_to TEXT,
                overwrite_of TEXT,
                superseded_by TEXT,
                trigger_policy_id TEXT,
                decay_policy_id TEXT,
                embedding_id TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        self.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_core_fts USING fts5(
                memory_id UNINDEXED,
                domain UNINDEXED,
                status UNINDEXED,
                scope UNINDEXED,
                title,
                body,
                tags,
                entities,
                tokenize = 'unicode61'
            )
            """
        )
        self.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_core_domain_status ON memory_core (domain, status)"
        )
        self.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_core_scope ON memory_core (scope)"
        )
        self.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_core_source_ref ON memory_core (source_ref)"
        )
        self.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_core_overwrite_of ON memory_core (overwrite_of)"
        )
        self.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_core_superseded_by ON memory_core (superseded_by)"
        )

    def insert_memory_core(self, memory: MemoryCore) -> str:
        """写入单个 MemoryCore，输入记忆对象并返回 memory_id。"""
        logger.info(
            "action=start memory_id=%s domain=%s memory_type=%s status=%s",
            memory.memory_id,
            memory.domain,
            memory.memory_type,
            memory.status,
        )
        self.execute(
            """
            INSERT INTO memory_core (
                memory_id,
                domain,
                memory_type,
                scope,
                source_type,
                source_ref,
                source_event_id,
                content_text,
                summary_text,
                entities_json,
                tags_json,
                importance,
                confidence,
                freshness_score,
                status,
                valid_from,
                valid_to,
                overwrite_of,
                superseded_by,
                trigger_policy_id,
                decay_policy_id,
                embedding_id,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory.memory_id,
                memory.domain,
                memory.memory_type,
                memory.scope,
                memory.source_type,
                memory.source_ref,
                memory.source_event_id,
                memory.content_text,
                memory.summary_text,
                json.dumps(memory.entities, ensure_ascii=True),
                json.dumps(memory.tags, ensure_ascii=True),
                memory.importance,
                memory.confidence,
                memory.freshness_score,
                memory.status,
                memory.valid_from,
                memory.valid_to,
                memory.overwrite_of,
                memory.superseded_by,
                memory.trigger_policy_id,
                memory.decay_policy_id,
                memory.embedding_id,
                memory.created_at,
                memory.updated_at,
            ),
        )
        logger.info(
            "action=inserted memory_id=%s",
            memory.memory_id,
        )
        self._upsert_fts(memory)
        return memory.memory_id

    def get_memory(self, memory_id: str) -> dict[str, Any] | None:
        """按 memory_id 查询记忆，返回反序列化后的行字典。"""
        row = self.fetch_one(
            "SELECT * FROM memory_core WHERE memory_id = ?",
            (memory_id,),
        )
        return self._deserialize_row(row)

    def batch_get_memories(self, memory_ids: list[str]) -> list[dict[str, Any]]:
        """批量按 memory_id 查询记忆，返回顺序尽量匹配输入 ID 列表。"""
        if not memory_ids:
            return []
        placeholders = ", ".join("?" for _ in memory_ids)
        rows = self.fetch_all(
            f"SELECT * FROM memory_core WHERE memory_id IN ({placeholders})",
            tuple(memory_ids),
        )
        row_map = {
            row["memory_id"]: self._deserialize_row(row)
            for row in rows
        }
        return [row_map[memory_id] for memory_id in memory_ids if memory_id in row_map]

    def update_memory_status(self, memory_id: str, status: str) -> None:
        """按 memory_id 更新记忆状态，输入目标状态字符串。"""
        self.execute(
            """
            UPDATE memory_core
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE memory_id = ?
            """,
            (status, memory_id),
        )
        self._sync_fts_from_row(memory_id)

    def mark_superseded(self, old_memory_id: str, new_memory_id: str) -> None:
        """建立新旧记忆覆盖关系，输入旧 memory_id 和新 memory_id。"""
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE memory_core
                SET status = 'superseded',
                    superseded_by = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE memory_id = ?
                """,
                (new_memory_id, old_memory_id),
            )
            connection.execute(
                """
                UPDATE memory_core
                SET overwrite_of = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE memory_id = ?
                """,
                (old_memory_id, new_memory_id),
            )
        self._sync_fts_from_row(old_memory_id)
        self._sync_fts_from_row(new_memory_id)

    def update_confidence(self, memory_id: str, confidence: float) -> None:
        """按 memory_id 更新置信度分数。"""
        self.execute(
            """
            UPDATE memory_core
            SET confidence = ?, updated_at = CURRENT_TIMESTAMP
            WHERE memory_id = ?
            """,
            (confidence, memory_id),
        )

    def update_importance(self, memory_id: str, importance: float) -> None:
        """按 memory_id 更新重要性分数。"""
        self.execute(
            """
            UPDATE memory_core
            SET importance = ?, updated_at = CURRENT_TIMESTAMP
            WHERE memory_id = ?
            """,
            (importance, memory_id),
        )

    def list_active_memories(
        self,
        domain: str | None = None,
        scope: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """列出 active 状态记忆，可按 domain 和 scope 过滤。"""
        logger.info(
            "action=start domain=%s scope=%s limit=%s",
            domain,
            scope,
            limit,
        )
        clauses = ["status = 'active'"]
        parameters: list[Any] = []
        if domain is not None:
            clauses.append("domain = ?")
            parameters.append(domain)
        if scope is not None:
            clauses.append("scope = ?")
            parameters.append(scope)
        sql = """
            SELECT * FROM memory_core
            WHERE {where_clause}
            ORDER BY updated_at DESC, created_at DESC
            LIMIT ?
        """.format(where_clause=" AND ".join(clauses))
        parameters.append(limit)
        rows = self.fetch_all(sql, tuple(parameters))
        result = [self._deserialize_row(row) for row in rows]
        logger.info(
            "action=done row_count=%s",
            len(result),
        )
        return result

    def search_memory_candidates(
        self,
        domain: str | None = None,
        status: str = "active",
        source_ref: str | None = None,
        entity_filters: dict[str, str] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """按 domain、status、source_ref 和 entity 字段搜索候选记忆。"""
        clauses = ["status = ?"]
        parameters: list[Any] = [status]
        if domain is not None:
            clauses.append("domain = ?")
            parameters.append(domain)
        if source_ref is not None:
            clauses.append("source_ref = ?")
            parameters.append(source_ref)
        if entity_filters:
            for key, value in entity_filters.items():
                clauses.append("entities_json LIKE ?")
                parameters.append(f"%{key}:{value}%")
        sql = """
            SELECT * FROM memory_core
            WHERE {where_clause}
            ORDER BY updated_at DESC, created_at DESC
            LIMIT ?
        """.format(where_clause=" AND ".join(clauses))
        parameters.append(limit)
        rows = self.fetch_all(sql, tuple(parameters))
        return [self._deserialize_row(row) for row in rows]

    def get_version_chain(self, memory_id: str) -> list[dict[str, Any]]:
        """查询指定 memory_id 的覆盖版本链，返回按时间排序的记忆列表。"""
        rows = self.fetch_all(
            """
            WITH RECURSIVE version_chain AS (
                SELECT * FROM memory_core WHERE memory_id = ?
                UNION
                SELECT m.*
                FROM memory_core m
                JOIN version_chain vc
                  ON m.memory_id = vc.overwrite_of
                  OR m.overwrite_of = vc.memory_id
                  OR m.memory_id = vc.superseded_by
                  OR m.superseded_by = vc.memory_id
            )
            SELECT DISTINCT * FROM version_chain
            """,
            (memory_id,),
        )
        items = [self._deserialize_row(row) for row in rows]
        items.sort(
            key=lambda item: (
                item["created_at"] or "",
                item["updated_at"] or "",
                item["memory_id"],
            )
        )
        return items

    def delete_memory(self, memory_id: str) -> None:
        """按 memory_id 删除单条 MemoryCore 记录。"""
        self._delete_fts(memory_id)
        self.execute(
            "DELETE FROM memory_core WHERE memory_id = ?",
            (memory_id,),
        )

    def search_bm25(
        self,
        query_text: str,
        *,
        domain: str | None = None,
        status: str | None = "active",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """使用 SQLite FTS5 BM25 搜索 MemoryCore，返回正向归一化分数。"""
        if limit < 1:
            raise ValueError("limit must be greater than 0")
        fts_query = self._build_fts_query(query_text)
        if not fts_query:
            return []
        clauses = ["memory_core_fts MATCH ?"]
        parameters: list[Any] = [fts_query]
        if domain is not None:
            clauses.append("domain = ?")
            parameters.append(domain)
        if status is not None:
            clauses.append("status = ?")
            parameters.append(status)
        sql = """
            SELECT
                memory_id,
                domain,
                status,
                bm25(memory_core_fts, 0.0, 0.0, 0.0, 0.0, 4.0, 1.0, 1.5, 1.5) AS raw_score
            FROM memory_core_fts
            WHERE {where_clause}
            ORDER BY raw_score ASC
            LIMIT ?
        """.format(where_clause=" AND ".join(clauses))
        parameters.append(limit)
        rows = self.fetch_all(sql, tuple(parameters))
        if not rows:
            return []
        raw_scores = [float(row["raw_score"]) for row in rows]
        raw_min = min(raw_scores)
        raw_max = max(raw_scores)
        raw_range = raw_max - raw_min or 1.0
        result: list[dict[str, Any]] = []
        for row in rows:
            raw = float(row["raw_score"])
            normalized = (raw_max - raw) / raw_range if len(rows) > 1 else 1.0
            result.append(
                {
                    "memory_id": row["memory_id"],
                    "domain": row["domain"],
                    "status": row["status"],
                    "bm25_score": round(normalized, 4),
                    "raw_score": raw,
                }
            )
        return result

    def _deserialize_row(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        """反序列化 MemoryCore 行中的 entities/tags JSON 字段。"""
        if row is None:
            return None
        row["entities_json"] = json.loads(row["entities_json"])
        row["tags_json"] = json.loads(row["tags_json"])
        row["entities"] = row["entities_json"]
        row["tags"] = row["tags_json"]
        return row

    def _upsert_fts(self, memory: MemoryCore) -> None:
        """同步写入 MemoryCore 的 FTS5 索引行。"""
        self._delete_fts(memory.memory_id)
        self.execute(
            """
            INSERT INTO memory_core_fts (
                memory_id,
                domain,
                status,
                scope,
                title,
                body,
                tags,
                entities
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory.memory_id,
                memory.domain,
                memory.status,
                memory.scope,
                memory.summary_text or "",
                memory.content_text,
                " ".join(memory.tags),
                " ".join(memory.entities),
            ),
        )

    def _sync_fts_from_row(self, memory_id: str) -> None:
        """从 memory_core 当前行重建指定 memory_id 的 FTS5 索引行。"""
        row = self.get_memory(memory_id)
        if row is None:
            self._delete_fts(memory_id)
            return
        memory = MemoryCore(
            memory_id=row["memory_id"],
            domain=row["domain"],
            memory_type=row["memory_type"],
            scope=row["scope"],
            source_type=row["source_type"],
            source_ref=row["source_ref"],
            source_event_id=row.get("source_event_id"),
            content_text=row["content_text"],
            summary_text=row.get("summary_text"),
            entities=list(row.get("entities") or []),
            tags=list(row.get("tags") or []),
            importance=float(row.get("importance", 0.5) or 0.0),
            confidence=float(row.get("confidence", 0.5) or 0.0),
            freshness_score=row.get("freshness_score"),
            status=row.get("status", "active"),
            valid_from=row.get("valid_from"),
            valid_to=row.get("valid_to"),
            overwrite_of=row.get("overwrite_of"),
            superseded_by=row.get("superseded_by"),
            trigger_policy_id=row.get("trigger_policy_id"),
            decay_policy_id=row.get("decay_policy_id"),
            embedding_id=row.get("embedding_id"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )
        self._upsert_fts(memory)

    def _delete_fts(self, memory_id: str) -> None:
        """删除指定 memory_id 的 FTS5 索引行。"""
        self.execute(
            "DELETE FROM memory_core_fts WHERE memory_id = ?",
            (memory_id,),
        )

    def _build_fts_query(self, query_text: str) -> str:
        """将用户查询转换成保守的 FTS5 MATCH 表达式。"""
        terms = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_\-]{2,}", clean_text(query_text))
        seen: set[str] = set()
        escaped: list[str] = []
        for term in terms:
            normalized = term.strip().strip("-_")
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            escaped.append(f'"{normalized.replace(chr(34), chr(34) + chr(34))}"')
        return " OR ".join(escaped)
