from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from src.schemas import MemoryCore
from src.utils.ids import memory_id
from src.utils.text import clean_text, truncate_text
from src.utils.time import utc_now_iso


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
    """Structured domain model for team_retention memory."""

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
