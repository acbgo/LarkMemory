from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Literal

from src.schemas import MemoryCore
from src.utils.ids import memory_id, new_id
from src.utils.text import clean_text, truncate_text
from src.utils.time import format_iso, parse_iso, utc_now_iso

from .base import SQLiteStore


RetentionFactType = Literal[
    "api_key",
    "customer_preference",
    "competitor_update",
    "compliance",
    "deadline",
    "risk",
    "team_fact",
]
RetentionRiskLevel = Literal["low", "medium", "high"]
RetentionReviewPolicy = Literal["ebbinghaus", "fixed", "none"]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = clean_text(value)
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _field_from_terms(terms: list[str], prefix: str) -> str | None:
    marker = f"{prefix}:"
    for term in terms:
        if term.startswith(marker):
            return term[len(marker):]
    return None


@dataclass(slots=True)
class TeamRetentionMemory:
    """Structured storage model for team_retention domain memory."""

    retention_id: str = field(default_factory=memory_id)
    team_id: str | None = None
    project_id: str | None = None
    workspace_id: str | None = None
    thread_id: str | None = None
    fact_type: RetentionFactType = "team_fact"
    fact_value: str = ""
    risk_level: RetentionRiskLevel = "medium"
    owner: str | None = None
    remember_reason: str | None = None
    review_policy: RetentionReviewPolicy = "ebbinghaus"
    review_count: int = 0
    last_review_at: str | None = None
    next_review_at: str | None = None
    expiry_time: str | None = None
    version_group: str | None = None
    source_event_id: str | None = None
    source_type: str = "feishu_chat"
    source_ref: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    tags: list[str] = field(default_factory=list)
    confidence: float = 0.7
    importance: float = 0.8
    overwrite_of: str | None = None
    superseded_by: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None

    def to_memory_core(self) -> MemoryCore:
        scope = "team" if self.team_id else "project" if self.project_id else "workspace"
        entities = _unique(
            [
                *( [f"team_id:{self.team_id}", self.team_id] if self.team_id else [] ),
                *( [f"project_id:{self.project_id}", self.project_id] if self.project_id else [] ),
                *( [f"workspace_id:{self.workspace_id}", self.workspace_id] if self.workspace_id else [] ),
                *( [f"thread_id:{self.thread_id}", self.thread_id] if self.thread_id else [] ),
                *( [f"owner:{self.owner}", self.owner] if self.owner else [] ),
                *( [f"version_group:{self.version_group}", self.version_group] if self.version_group else [] ),
            ]
        )
        tags = _unique(
            [
                "team_retention",
                f"fact_type:{self.fact_type}",
                f"risk_level:{self.risk_level}",
                f"review_policy:{self.review_policy}",
                *self.tags,
            ]
        )
        now = utc_now_iso()
        return MemoryCore(
            memory_id=self.retention_id,
            domain="team_retention",
            memory_type="team_retention",
            scope=scope,  # type: ignore[arg-type]
            source_type=self.source_type,
            source_ref=self.source_ref or self.thread_id or self.team_id or self.project_id or "unknown",
            source_event_id=self.source_event_id,
            content_text=self.build_content_text(),
            summary_text=self.build_summary_text(),
            entities=entities,
            tags=tags,
            importance=_clamp(self.importance),
            confidence=_clamp(self.confidence),
            status="active",
            valid_from=self.valid_from or self.created_at,
            valid_to=self.valid_to or self.expiry_time,
            overwrite_of=self.overwrite_of,
            superseded_by=self.superseded_by,
            created_at=self.created_at or now,
            updated_at=now,
        )

    def build_content_text(self) -> str:
        lines = [
            f"Team retention memory: {self.fact_type}",
            f"Fact: {self.fact_value}",
            f"Risk: {self.risk_level}",
        ]
        if self.owner:
            lines.append(f"Owner: {self.owner}")
        if self.remember_reason:
            lines.append(f"Reason: {self.remember_reason}")
        if self.next_review_at:
            lines.append(f"Next review: {self.next_review_at}")
        if self.expiry_time:
            lines.append(f"Expiry: {self.expiry_time}")
        if self.source_ref:
            lines.append(f"Source: {self.source_ref}")
        return "\n".join(line for line in lines if line.strip())

    def build_summary_text(self) -> str:
        return truncate_text(clean_text(f"{self.fact_type}: {self.fact_value}"), 200)

    def to_card(self) -> dict[str, Any]:
        return {
            "type": "team_retention_card",
            "title": "Team memory review",
            "memory_id": self.retention_id,
            "fact_type": self.fact_type,
            "fact_value": self.fact_value,
            "risk_level": self.risk_level,
            "owner": self.owner,
            "team_id": self.team_id,
            "project_id": self.project_id,
            "next_review_at": self.next_review_at,
            "review_count": self.review_count,
            "source_ref": self.source_ref,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "retention_id": self.retention_id,
            "team_id": self.team_id,
            "project_id": self.project_id,
            "workspace_id": self.workspace_id,
            "thread_id": self.thread_id,
            "fact_type": self.fact_type,
            "fact_value": self.fact_value,
            "risk_level": self.risk_level,
            "owner": self.owner,
            "remember_reason": self.remember_reason,
            "review_policy": self.review_policy,
            "review_count": self.review_count,
            "last_review_at": self.last_review_at,
            "next_review_at": self.next_review_at,
            "expiry_time": self.expiry_time,
            "version_group": self.version_group,
            "source_event_id": self.source_event_id,
            "source_type": self.source_type,
            "source_ref": self.source_ref,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "tags": list(self.tags),
            "confidence": _clamp(self.confidence),
            "importance": _clamp(self.importance),
            "overwrite_of": self.overwrite_of,
            "superseded_by": self.superseded_by,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_memory_core(cls, memory: MemoryCore | dict[str, Any]) -> TeamRetentionMemory:
        data = memory if isinstance(memory, dict) else {
            name: getattr(memory, name)
            for name in MemoryCore.__dataclass_fields__
            if hasattr(memory, name)
        }
        entities = list(data.get("entities") or data.get("entities_json") or [])
        tags = list(data.get("tags") or data.get("tags_json") or [])
        fact_type = _field_from_terms(tags, "fact_type") or "team_fact"
        risk_level = _field_from_terms(tags, "risk_level") or "medium"
        review_policy = _field_from_terms(tags, "review_policy") or "ebbinghaus"
        content = str(data.get("content_text") or "")
        fact_value = content
        for line in content.splitlines():
            if line.startswith("Fact:"):
                fact_value = line.split(":", 1)[1].strip()
                break
        return cls(
            retention_id=str(data.get("memory_id")),
            team_id=_field_from_terms(entities, "team_id"),
            project_id=_field_from_terms(entities, "project_id"),
            workspace_id=_field_from_terms(entities, "workspace_id"),
            thread_id=_field_from_terms(entities, "thread_id"),
            fact_type=fact_type,  # type: ignore[arg-type]
            fact_value=fact_value,
            risk_level=risk_level,  # type: ignore[arg-type]
            owner=_field_from_terms(entities, "owner"),
            review_policy=review_policy,  # type: ignore[arg-type]
            version_group=_field_from_terms(entities, "version_group"),
            source_event_id=data.get("source_event_id"),
            source_type=str(data.get("source_type") or "feishu_chat"),
            source_ref=data.get("source_ref"),
            valid_from=data.get("valid_from"),
            valid_to=data.get("valid_to"),
            expiry_time=data.get("valid_to"),
            tags=[
                tag
                for tag in tags
                if not tag.startswith(("fact_type:", "risk_level:", "review_policy:"))
            ],
            confidence=float(data.get("confidence") or 0.0),
            importance=float(data.get("importance") or 0.0),
            overwrite_of=data.get("overwrite_of"),
            superseded_by=data.get("superseded_by"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass(slots=True)
class TeamReviewSchedule:
    schedule_id: str
    memory_id: str
    team_id: str | None = None
    project_id: str | None = None
    workspace_id: str | None = None
    review_policy: RetentionReviewPolicy = "ebbinghaus"
    risk_level: RetentionRiskLevel = "medium"
    next_review_at: str | None = None
    last_review_at: str | None = None
    review_count: int = 0
    active: bool = True
    created_at: str | None = None
    updated_at: str | None = None


class TeamRetentionStore(SQLiteStore):
    """Storage for TeamRetentionMemory and its review schedule."""

    def create_table(self) -> None:
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

    def create_review_schedule(self, memory: TeamRetentionMemory) -> str | None:
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
        row = self.fetch_one(
            "SELECT * FROM memory_review_schedule WHERE memory_id = ? AND domain = 'team_retention'",
            (memory_id,),
        )
        return self._row_to_schedule(row)

    def list_due_reviews(
        self,
        *,
        now: str | None = None,
        team_id: str | None = None,
        project_id: str | None = None,
        workspace_id: str | None = None,
        limit: int = 10,
    ) -> list[TeamReviewSchedule]:
        effective_now = now or utc_now_iso()
        clauses = [
            "domain = 'team_retention'",
            "active = 1",
            "next_review_at IS NOT NULL",
            "next_review_at <= ?",
        ]
        parameters: list[Any] = [effective_now]
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

    def snooze_review(self, memory_id: str, *, days: int = 1, now: str | None = None) -> str:
        if days <= 0:
            raise ValueError("days must be greater than 0")
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
