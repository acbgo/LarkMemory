from __future__ import annotations

import json
import logging
from typing import Any

from src.utils.time import utc_now_iso

from .base import SQLiteStore

logger = logging.getLogger(__name__)

DEFAULT_SOURCE_STATE_DB = ".larkmemory/source_state.db"


class SourceStateStore(SQLiteStore):
    """Source 层轻量处理状态 DB，记录外部资源的处理游标和内容指纹。

    独立于后端记忆引擎 DB（.larkmemory/source_state.db），
    只做"书签/游标/指纹"，不存储业务数据（事件、记忆）。

    使用场景：
      - 妙记 scanner：判断 meeting 是否已处理、AI 产物是否就绪。
      - 文档 processor：对比内容 hash 判断是否有实质变更。
    """

    def __init__(self, db_path: str = DEFAULT_SOURCE_STATE_DB) -> None:
        super().__init__(db_path)

    def create_table(self) -> None:
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS source_processed (
                source_type TEXT NOT NULL,
                external_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                last_hash TEXT,
                cursor_value TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                processed_at TEXT NOT NULL DEFAULT '',
                error_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (source_type, external_id)
            )
            """
        )
        self.execute(
            "CREATE INDEX IF NOT EXISTS idx_source_processed_status "
            "ON source_processed (source_type, status)"
        )

    # ---- 写入 ----

    def upsert_state(
        self,
        source_type: str,
        external_id: str,
        status: str = "pending",
        last_hash: str | None = None,
        cursor_value: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        now = utc_now_iso()
        self.execute(
            """
            INSERT INTO source_processed
                (source_type, external_id, status, last_hash, cursor_value,
                 metadata_json, processed_at, error_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(source_type, external_id) DO UPDATE SET
                status = excluded.status,
                last_hash = COALESCE(excluded.last_hash, source_processed.last_hash),
                cursor_value = COALESCE(excluded.cursor_value, source_processed.cursor_value),
                metadata_json = excluded.metadata_json,
                processed_at = excluded.processed_at,
                error_count = 0
            """,
            (
                source_type, external_id, status,
                last_hash, cursor_value,
                json.dumps(metadata or {}, ensure_ascii=True), now,
            ),
        )

    # ---- 单条查询 ----

    def get_state(self, source_type: str, external_id: str) -> dict[str, Any] | None:
        row = self.fetch_one(
            "SELECT * FROM source_processed WHERE source_type = ? AND external_id = ?",
            (source_type, external_id),
        )
        return self._deserialize(row)

    # ---- 批量查询 ----

    def list_pending(
        self, source_type: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        rows = self.fetch_all(
            """
            SELECT * FROM source_processed
            WHERE source_type = ? AND status IN ('pending', 'pending_ai', 'partial', 'error')
            ORDER BY processed_at ASC
            LIMIT ?
            """,
            (source_type, limit),
        )
        return [self._deserialize(r) for r in rows]

    def list_by_status(
        self, source_type: str, status: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        rows = self.fetch_all(
            """
            SELECT * FROM source_processed
            WHERE source_type = ? AND status = ?
            ORDER BY processed_at DESC
            LIMIT ?
            """,
            (source_type, status, limit),
        )
        return [self._deserialize(r) for r in rows]

    # ---- 状态更新 ----

    def mark_complete(self, source_type: str, external_id: str) -> None:
        self.execute(
            "UPDATE source_processed SET status = 'complete', processed_at = ? "
            "WHERE source_type = ? AND external_id = ?",
            (utc_now_iso(), source_type, external_id),
        )

    def mark_error(self, source_type: str, external_id: str) -> None:
        self.execute(
            "UPDATE source_processed SET status = 'error', "
            "error_count = error_count + 1, processed_at = ? "
            "WHERE source_type = ? AND external_id = ?",
            (utc_now_iso(), source_type, external_id),
        )

    def reset_error(self, source_type: str, external_id: str) -> None:
        self.execute(
            "UPDATE source_processed SET error_count = 0 "
            "WHERE source_type = ? AND external_id = ?",
            (source_type, external_id),
        )

    def update_cursor(
        self, source_type: str, external_id: str, cursor_value: str
    ) -> None:
        self.execute(
            "UPDATE source_processed SET cursor_value = ?, processed_at = ? "
            "WHERE source_type = ? AND external_id = ?",
            (cursor_value, utc_now_iso(), source_type, external_id),
        )

    def update_hash(
        self, source_type: str, external_id: str, last_hash: str
    ) -> None:
        self.execute(
            "UPDATE source_processed SET last_hash = ?, processed_at = ? "
            "WHERE source_type = ? AND external_id = ?",
            (last_hash, utc_now_iso(), source_type, external_id),
        )

    # ---- 清理 ----

    def delete_states_before(self, before_days: int = 30) -> int:
        with self.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM source_processed "
                "WHERE processed_at < datetime('now', '-' || ? || ' days')",
                (str(before_days),),
            )
            return cursor.rowcount

    # ---- 内部 ----

    def _deserialize(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        row = dict(row)
        row["metadata"] = json.loads(row.get("metadata_json", "{}"))
        return row
