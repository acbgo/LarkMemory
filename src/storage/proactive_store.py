from __future__ import annotations

import json
from typing import Any

from .base import SQLiteStore


class ProactiveStore(SQLiteStore):
    """持久化主动推送状态，提供幂等检查和排障查询。"""

    def create_table(self) -> None:
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS proactive_push (
                event_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                push_type TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT,
                memory_id TEXT,
                related_memory_ids_json TEXT,
                target_chat_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (event_id, push_type)
            )
            """
        )

    def upsert_record(
        self,
        *,
        event_id: str,
        domain: str,
        push_type: str,
        status: str,
        reason: str | None = None,
        memory_id: str | None = None,
        related_memory_ids: list[str] | None = None,
        target_chat_id: str | None = None,
    ) -> None:
        self.execute(
            """
            INSERT INTO proactive_push (
                event_id, domain, push_type, status, reason, memory_id,
                related_memory_ids_json, target_chat_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id, push_type) DO UPDATE SET
                domain = excluded.domain,
                status = excluded.status,
                reason = excluded.reason,
                memory_id = excluded.memory_id,
                related_memory_ids_json = excluded.related_memory_ids_json,
                target_chat_id = excluded.target_chat_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                event_id,
                domain,
                push_type,
                status,
                reason,
                memory_id,
                json.dumps(related_memory_ids or [], ensure_ascii=False),
                target_chat_id,
            ),
        )

    def get_record(self, event_id: str, push_type: str) -> dict[str, Any] | None:
        row = self.fetch_one(
            """
            SELECT
                event_id,
                domain,
                push_type,
                status,
                reason,
                memory_id,
                related_memory_ids_json,
                target_chat_id,
                created_at,
                updated_at
            FROM proactive_push
            WHERE event_id = ? AND push_type = ?
            """,
            (event_id, push_type),
        )
        if row is None:
            return None
        raw_ids = row.pop("related_memory_ids_json", None)
        row["related_memory_ids"] = json.loads(raw_ids) if raw_ids else []
        return row

    def is_sent(self, event_id: str, push_type: str) -> bool:
        row = self.get_record(event_id, push_type)
        return bool(row and row.get("status") == "sent")
