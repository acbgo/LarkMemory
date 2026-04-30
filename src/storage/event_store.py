from __future__ import annotations

import json
import logging
from typing import Any

from src.schemas import NormalizedEvent

from .base import SQLiteStore


logger = logging.getLogger(__name__)


class EventStore(SQLiteStore):
    def create_table(self) -> None:
        """创建事件存储表和常用索引，供 NormalizedEvent 持久化使用。"""
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS event_store (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                source_type TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                user_id TEXT,
                session_id TEXT,
                project_id TEXT,
                team_id TEXT,
                workspace_id TEXT,
                repo_id TEXT,
                thread_id TEXT,
                scope TEXT NOT NULL,
                title TEXT,
                content_text TEXT,
                payload_json TEXT NOT NULL,
                raw_payload_json TEXT NOT NULL,
                tags_json TEXT NOT NULL
            )
            """
        )
        self.execute(
            "CREATE INDEX IF NOT EXISTS idx_event_store_source_type ON event_store (source_type)"
        )
        self.execute(
            "CREATE INDEX IF NOT EXISTS idx_event_store_occurred_at ON event_store (occurred_at)"
        )
        self.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_event_store_scope_lookup
            ON event_store (project_id, team_id, user_id, occurred_at)
            """
        )

    def insert_event(self, event: NormalizedEvent) -> str:
        """写入单个 NormalizedEvent，输入事件对象并返回 event_id。"""
        logger.info(
            "action=start event_id=%s event_type=%s source_type=%s",
            event.event_id,
            event.event_type,
            event.source_type,
        )
        self.execute(
            """
            INSERT INTO event_store (
                event_id,
                event_type,
                source_type,
                occurred_at,
                user_id,
                session_id,
                project_id,
                team_id,
                workspace_id,
                repo_id,
                thread_id,
                scope,
                title,
                content_text,
                payload_json,
                raw_payload_json,
                tags_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.event_type,
                event.source_type,
                event.occurred_at,
                event.context.user_id,
                event.context.session_id,
                event.context.project_id,
                event.context.team_id,
                event.context.workspace_id,
                event.context.repo_id,
                event.context.thread_id,
                event.context.scope,
                event.title,
                event.content_text,
                json.dumps(event.payload, ensure_ascii=True),
                json.dumps(event.raw_payload, ensure_ascii=True),
                json.dumps(event.tags, ensure_ascii=True),
            ),
        )
        logger.info(
            "action=inserted event_id=%s",
            event.event_id,
        )
        return event.event_id

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        """按 event_id 查询事件，返回反序列化后的事件行字典。"""
        row = self.fetch_one(
            "SELECT * FROM event_store WHERE event_id = ?",
            (event_id,),
        )
        return self._deserialize_row(row)

    def list_events(self, limit: int = 100) -> list[dict[str, Any]]:
        """按 occurred_at 倒序列出事件，输入最大返回数量。"""
        rows = self.fetch_all(
            """
            SELECT * FROM event_store
            ORDER BY occurred_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [self._deserialize_row(row) for row in rows]

    def list_events_by_source(
        self,
        source_type: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """按 source_type 过滤事件并按时间倒序返回。"""
        rows = self.fetch_all(
            """
            SELECT * FROM event_store
            WHERE source_type = ?
            ORDER BY occurred_at DESC
            LIMIT ?
            """,
            (source_type, limit),
        )
        return [self._deserialize_row(row) for row in rows]

    def list_events_for_scope(
        self,
        project_id: str | None = None,
        team_id: str | None = None,
        user_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """按项目、团队或用户范围过滤事件，返回时间倒序列表。"""
        clauses: list[str] = []
        parameters: list[Any] = []

        if project_id is not None:
            clauses.append("project_id = ?")
            parameters.append(project_id)
        if team_id is not None:
            clauses.append("team_id = ?")
            parameters.append(team_id)
        if user_id is not None:
            clauses.append("user_id = ?")
            parameters.append(user_id)

        sql = "SELECT * FROM event_store"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY occurred_at DESC LIMIT ?"
        parameters.append(limit)

        rows = self.fetch_all(sql, tuple(parameters))
        return [self._deserialize_row(row) for row in rows]

    def list_events_by_time_range(
        self,
        start_at: str,
        end_at: str,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """查询指定时间范围内的事件，输入起止 ISO 时间和返回上限。"""
        rows = self.fetch_all(
            """
            SELECT * FROM event_store
            WHERE occurred_at >= ? AND occurred_at <= ?
            ORDER BY occurred_at DESC
            LIMIT ?
            """,
            (start_at, end_at, limit),
        )
        return [self._deserialize_row(row) for row in rows]

    def delete_old_events(self, before: str) -> int:
        """删除早于 before 时间的事件，返回删除行数。"""
        with self.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM event_store WHERE occurred_at < ?",
                (before,),
            )
            return cursor.rowcount

    def _deserialize_row(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        """反序列化事件行中的 JSON 字段，未命中行时返回 None。"""
        if row is None:
            return None
        row["payload_json"] = json.loads(row["payload_json"])
        row["raw_payload_json"] = json.loads(row["raw_payload_json"])
        row["tags_json"] = json.loads(row["tags_json"])
        row["payload"] = row["payload_json"]
        row["raw_payload"] = row["raw_payload_json"]
        row["tags"] = row["tags_json"]
        return row
