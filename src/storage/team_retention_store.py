from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from src.domains.team_retention.models import TeamRetentionMemory, TeamReviewSchedule
from src.utils.ids import new_id
from src.utils.time import format_iso, parse_iso, utc_now_iso

from .base import SQLiteStore


class TeamRetentionStore(SQLiteStore):
    """Storage for TeamRetentionMemory and its review schedule."""

    def create_table(self) -> None:
        """创建团队留存记忆表和复习排期表。"""
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_team_retention (
                memory_id TEXT PRIMARY KEY,
                team_id TEXT,
                project_id TEXT,
                workspace_id TEXT,
                thread_id TEXT,
                fact_type TEXT NOT NULL,
                fact_value TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                owner TEXT,
                remember_reason TEXT,
                review_policy TEXT NOT NULL,
                review_count INTEGER NOT NULL,
                last_review_at TEXT,
                next_review_at TEXT,
                expiry_time TEXT,
                version_group TEXT,
                source_event_id TEXT,
                source_type TEXT NOT NULL,
                source_ref TEXT,
                valid_from TEXT,
                valid_to TEXT,
                tags_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                importance REAL NOT NULL,
                overwrite_of TEXT,
                superseded_by TEXT,
                metadata_json TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        self.execute("CREATE INDEX IF NOT EXISTS idx_team_retention_team ON memory_team_retention (team_id)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_team_retention_project ON memory_team_retention (project_id)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_team_retention_fact ON memory_team_retention (fact_type)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_team_retention_version ON memory_team_retention (version_group)")
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_review_schedule (
                schedule_id TEXT PRIMARY KEY,
                memory_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                team_id TEXT,
                project_id TEXT,
                workspace_id TEXT,
                review_policy TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                next_review_at TEXT,
                last_review_at TEXT,
                review_count INTEGER NOT NULL,
                active INTEGER NOT NULL,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        self.execute("CREATE INDEX IF NOT EXISTS idx_review_due ON memory_review_schedule (active, next_review_at)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_review_memory ON memory_review_schedule (memory_id)")

    def insert_memory(self, memory: TeamRetentionMemory) -> str:
        """写入 TeamRetentionMemory，输入领域模型并返回 retention_id。"""
        now = utc_now_iso()
        created = memory.created_at or now
        updated = memory.updated_at or now
        self.execute(
            """
            INSERT INTO memory_team_retention (
                memory_id, team_id, project_id, workspace_id, thread_id,
                fact_type, fact_value, risk_level, owner, remember_reason,
                review_policy, review_count, last_review_at, next_review_at,
                expiry_time, version_group, source_event_id, source_type,
                source_ref, valid_from, valid_to, tags_json, confidence,
                importance, overwrite_of, superseded_by, metadata_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory.retention_id,
                memory.team_id,
                memory.project_id,
                memory.workspace_id,
                memory.thread_id,
                memory.fact_type,
                memory.fact_value,
                memory.risk_level,
                memory.owner,
                memory.remember_reason,
                memory.review_policy,
                memory.review_count,
                memory.last_review_at,
                memory.next_review_at,
                memory.expiry_time,
                memory.version_group,
                memory.source_event_id,
                memory.source_type,
                memory.source_ref,
                memory.valid_from,
                memory.valid_to,
                json.dumps(memory.tags, ensure_ascii=True),
                memory.confidence,
                memory.importance,
                memory.overwrite_of,
                memory.superseded_by,
                json.dumps(memory.metadata, ensure_ascii=True),
                created,
                updated,
            ),
        )
        return memory.retention_id

    def get_memory(self, memory_id: str) -> TeamRetentionMemory | None:
        """按 memory_id 查询团队留存记忆，返回领域模型或 None。"""
        row = self.fetch_one(
            "SELECT * FROM memory_team_retention WHERE memory_id = ?",
            (memory_id,),
        )
        return self._row_to_memory(row)

    def list_memories(
        self,
        *,
        team_id: str | None = None,
        project_id: str | None = None,
        workspace_id: str | None = None,
        fact_type: str | None = None,
        version_group: str | None = None,
        limit: int = 100,
    ) -> list[TeamRetentionMemory]:
        """按团队、项目、工作区、事实类型或版本组过滤团队留存记忆。"""
        clauses: list[str] = []
        parameters: list[Any] = []
        for column, value in (
            ("team_id", team_id),
            ("project_id", project_id),
            ("workspace_id", workspace_id),
            ("fact_type", fact_type),
            ("version_group", version_group),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                parameters.append(value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(limit)
        rows = self.fetch_all(
            f"""
            SELECT * FROM memory_team_retention
            {where}
            ORDER BY updated_at DESC, created_at DESC
            LIMIT ?
            """,
            tuple(parameters),
        )
        return [item for item in (self._row_to_memory(row) for row in rows) if item is not None]

    def update_memory_links(
        self,
        memory_id: str,
        *,
        overwrite_of: str | None = None,
        superseded_by: str | None = None,
    ) -> None:
        """更新团队留存记忆的 overwrite_of 和 superseded_by 链接字段。"""
        self.execute(
            """
            UPDATE memory_team_retention
            SET overwrite_of = COALESCE(?, overwrite_of),
                superseded_by = COALESCE(?, superseded_by),
                updated_at = CURRENT_TIMESTAMP
            WHERE memory_id = ?
            """,
            (overwrite_of, superseded_by, memory_id),
        )

    def update_memory_metadata(
        self,
        memory_id: str,
        metadata: dict[str, Any],
    ) -> None:
        """按 memory_id 更新团队留存记忆 metadata_json 和 updated_at。"""
        self.execute(
            """
            UPDATE memory_team_retention
            SET metadata_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE memory_id = ?
            """,
            (json.dumps(metadata, ensure_ascii=True), memory_id),
        )

    def create_review_schedule(self, memory: TeamRetentionMemory) -> str | None:
        """为团队留存记忆创建复习排期，review_policy 为 none 时返回 None。"""
        if memory.review_policy == "none":
            return None
        next_review_at = memory.next_review_at or self.next_review_time(
            memory.created_at or utc_now_iso(),
            review_count=memory.review_count,
            risk_level=memory.risk_level,
            review_policy=memory.review_policy,
        )
        schedule_id = new_id("sched")
        now = utc_now_iso()
        self.execute(
            """
            INSERT INTO memory_review_schedule (
                schedule_id, memory_id, domain, team_id, project_id, workspace_id,
                review_policy, risk_level, next_review_at, last_review_at,
                review_count, active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                schedule_id,
                memory.retention_id,
                "team_retention",
                memory.team_id,
                memory.project_id,
                memory.workspace_id,
                memory.review_policy,
                memory.risk_level,
                next_review_at,
                memory.last_review_at,
                memory.review_count,
                1,
                now,
                now,
            ),
        )
        self.execute(
            """
            UPDATE memory_team_retention
            SET next_review_at = ?, updated_at = CURRENT_TIMESTAMP
            WHERE memory_id = ?
            """,
            (next_review_at, memory.retention_id),
        )
        return schedule_id

    def get_review_schedule(self, memory_id: str) -> TeamReviewSchedule | None:
        """按 memory_id 查询团队留存复习排期，返回排期模型或 None。"""
        row = self.fetch_one(
            "SELECT * FROM memory_review_schedule WHERE memory_id = ? AND domain = 'team_retention'",
            (memory_id,),
        )
        return self._row_to_schedule(row)

    def list_due_reviews(
        self,
        *,
        now: str | None = None,
        warning_window_hours: int = 0,
        team_id: str | None = None,
        project_id: str | None = None,
        workspace_id: str | None = None,
        limit: int = 10,
    ) -> list[TeamReviewSchedule]:
        """查询到期或即将到期的复习排期，可按团队、项目和工作区过滤。"""
        effective_now = now or utc_now_iso()
        cutoff = effective_now
        if warning_window_hours > 0:
            cutoff = format_iso(parse_iso(effective_now) + timedelta(hours=warning_window_hours))
        clauses = [
            "domain = 'team_retention'",
            "active = 1",
            "next_review_at IS NOT NULL",
            "next_review_at <= ?",
        ]
        parameters: list[Any] = [cutoff]
        for column, value in (
            ("team_id", team_id),
            ("project_id", project_id),
            ("workspace_id", workspace_id),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                parameters.append(value)
        parameters.append(limit)
        rows = self.fetch_all(
            f"""
            SELECT * FROM memory_review_schedule
            WHERE {' AND '.join(clauses)}
            ORDER BY next_review_at ASC
            LIMIT ?
            """,
            tuple(parameters),
        )
        return [item for item in (self._row_to_schedule(row) for row in rows) if item is not None]

    def mark_reviewed(self, memory_id: str, *, reviewed_at: str | None = None) -> str:
        """标记指定记忆已复习，输入 memory_id 和可选复习时间，返回下次复习时间。"""
        schedule = self.get_review_schedule(memory_id)
        if schedule is None:
            raise ValueError(f"review schedule not found: {memory_id}")
        effective_reviewed_at = reviewed_at or utc_now_iso()
        next_review_at = self.next_review_time(
            effective_reviewed_at,
            review_count=schedule.review_count + 1,
            risk_level=schedule.risk_level,
            review_policy=schedule.review_policy,
        )
        self.execute(
            """
            UPDATE memory_review_schedule
            SET last_review_at = ?,
                next_review_at = ?,
                review_count = review_count + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE memory_id = ? AND domain = 'team_retention'
            """,
            (effective_reviewed_at, next_review_at, memory_id),
        )
        self.execute(
            """
            UPDATE memory_team_retention
            SET last_review_at = ?,
                next_review_at = ?,
                review_count = review_count + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE memory_id = ?
            """,
            (effective_reviewed_at, next_review_at, memory_id),
        )
        return next_review_at

    def reinforce_review(self, memory_id: str, *, observed_at: str | None = None) -> str:
        """按重复观察时间强化团队记忆复习曲线，返回新的下次复习时间。"""
        if self.get_memory(memory_id) is None:
            raise ValueError(f"team retention memory not found: {memory_id}")
        return self.mark_reviewed(memory_id, reviewed_at=observed_at)

    def snooze_review(self, memory_id: str, *, days: int = 1, now: str | None = None) -> str:
        """将指定记忆复习时间顺延 days 天，返回新的下次复习时间。"""
        if days <= 0:
            raise ValueError("days must be greater than 0")
        if self.get_review_schedule(memory_id) is None:
            raise ValueError(f"review schedule not found: {memory_id}")
        reference = parse_iso(now or utc_now_iso())
        next_review_at = format_iso(reference + timedelta(days=days))
        self.execute(
            """
            UPDATE memory_review_schedule
            SET next_review_at = ?, updated_at = CURRENT_TIMESTAMP
            WHERE memory_id = ? AND domain = 'team_retention'
            """,
            (next_review_at, memory_id),
        )
        self.execute(
            """
            UPDATE memory_team_retention
            SET next_review_at = ?, updated_at = CURRENT_TIMESTAMP
            WHERE memory_id = ?
            """,
            (next_review_at, memory_id),
        )
        return next_review_at

    def deactivate_review(self, memory_id: str) -> None:
        """按 memory_id 停用团队留存复习排期。"""
        self.execute(
            """
            UPDATE memory_review_schedule
            SET active = 0, updated_at = CURRENT_TIMESTAMP
            WHERE memory_id = ? AND domain = 'team_retention'
            """,
            (memory_id,),
        )

    @staticmethod
    def next_review_time(
        reference_time: str,
        *,
        review_count: int,
        risk_level: str,
        review_policy: str,
    ) -> str:
        """根据参考时间、复习次数、风险等级和策略计算下次复习时间。"""
        if review_policy == "none":
            return reference_time
        if review_policy == "fixed":
            days = 7
        else:
            intervals = {
                "high": [1, 2, 4, 7, 14, 30],
                "medium": [1, 3, 7, 14, 30],
                "low": [3, 7, 14, 30],
            }.get(risk_level, [1, 3, 7, 14, 30])
            days = intervals[min(max(review_count, 0), len(intervals) - 1)]
        return format_iso(parse_iso(reference_time) + timedelta(days=days))

    def _row_to_memory(self, row: dict[str, Any] | None) -> TeamRetentionMemory | None:
        """将数据库行转换为 TeamRetentionMemory，输入 None 时返回 None。"""
        if row is None:
            return None
        return TeamRetentionMemory(
            retention_id=row["memory_id"],
            team_id=row.get("team_id"),
            project_id=row.get("project_id"),
            workspace_id=row.get("workspace_id"),
            thread_id=row.get("thread_id"),
            fact_type=row.get("fact_type") or "team_fact",
            fact_value=row.get("fact_value") or "",
            risk_level=row.get("risk_level") or "medium",
            owner=row.get("owner"),
            remember_reason=row.get("remember_reason"),
            review_policy=row.get("review_policy") or "ebbinghaus",
            review_count=int(row.get("review_count") or 0),
            last_review_at=row.get("last_review_at"),
            next_review_at=row.get("next_review_at"),
            expiry_time=row.get("expiry_time"),
            version_group=row.get("version_group"),
            source_event_id=row.get("source_event_id"),
            source_type=row.get("source_type") or "feishu_chat",
            source_ref=row.get("source_ref"),
            valid_from=row.get("valid_from"),
            valid_to=row.get("valid_to"),
            tags=json.loads(row.get("tags_json") or "[]"),
            confidence=float(row.get("confidence") or 0.0),
            importance=float(row.get("importance") or 0.0),
            overwrite_of=row.get("overwrite_of"),
            superseded_by=row.get("superseded_by"),
            metadata=json.loads(row.get("metadata_json") or "{}"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    def _row_to_schedule(self, row: dict[str, Any] | None) -> TeamReviewSchedule | None:
        """将数据库行转换为 TeamReviewSchedule，输入 None 时返回 None。"""
        if row is None:
            return None
        return TeamReviewSchedule(
            schedule_id=row["schedule_id"],
            memory_id=row["memory_id"],
            team_id=row.get("team_id"),
            project_id=row.get("project_id"),
            workspace_id=row.get("workspace_id"),
            review_policy=row.get("review_policy") or "ebbinghaus",
            risk_level=row.get("risk_level") or "medium",
            next_review_at=row.get("next_review_at"),
            last_review_at=row.get("last_review_at"),
            review_count=int(row.get("review_count") or 0),
            active=bool(row.get("active")),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )
