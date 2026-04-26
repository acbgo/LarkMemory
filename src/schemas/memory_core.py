from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .event import ScopeType


MemoryDomain = Literal[
    "cli_workflow",
    "project_decision",
    "personal_preference",
    "team_retention",
]

MemoryStatus = Literal[
    "active",
    "candidate",
    "superseded",
    "expired",
    "forgotten",
]


@dataclass(slots=True)
class MemoryCore:
    memory_id: str
    domain: MemoryDomain
    memory_type: str
    scope: ScopeType
    source_type: str
    source_ref: str
    content_text: str
    source_event_id: str | None = None
    summary_text: str | None = None
    entities: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    importance: float = 0.0
    confidence: float = 0.0
    freshness_score: float | None = None
    status: MemoryStatus = "active"
    valid_from: str | None = None
    valid_to: str | None = None
    overwrite_of: str | None = None
    superseded_by: str | None = None
    trigger_policy_id: str | None = None
    decay_policy_id: str | None = None
    embedding_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
