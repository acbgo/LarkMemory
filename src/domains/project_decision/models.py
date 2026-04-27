from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from src.schemas import MemoryCore
from src.utils.ids import memory_id
from src.utils.text import clean_text, truncate_text
from src.utils.time import utc_now_iso


DecisionStatus = Literal["proposed", "confirmed", "rejected", "superseded", "unknown"]
DecisionConfidenceLevel = Literal["low", "medium", "high"]
DecisionRelationType = Literal[
    "supersedes",
    "superseded_by",
    "related_to",
    "blocks",
    "depends_on",
]
DecisionReasonType = Literal["support", "against", "constraint", "risk", "context"]


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


def _field_from_entities(entities: list[str], prefix: str) -> str | None:
    marker = f"{prefix}:"
    for entity in entities:
        if entity.startswith(marker):
            return entity[len(marker):]
    return None


def _line_value(text: str, label: str) -> str | None:
    prefix = f"{label}:"
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith(prefix):
            return line[len(prefix):].strip() or None
    return None


@dataclass(slots=True)
class DecisionAlternative:
    """A candidate option discussed in a project decision."""

    name: str
    description: str | None = None
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)
    status: DecisionStatus = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "pros": list(self.pros),
            "cons": list(self.cons),
            "status": self.status,
        }


@dataclass(slots=True)
class DecisionReason:
    """A reason, objection, risk, or contextual note for a decision."""

    text: str
    reason_type: DecisionReasonType = "context"
    source_ref: str | None = None
    speaker_id: str | None = None
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "reason_type": self.reason_type,
            "source_ref": self.source_ref,
            "speaker_id": self.speaker_id,
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class ProjectDecision:
    """Structured project decision memory for the project_decision domain."""

    decision_id: str = field(default_factory=memory_id)
    project_id: str | None = None
    workspace_id: str | None = None
    team_id: str | None = None
    thread_id: str | None = None
    topic: str = ""
    decision: str = ""
    conclusion: str | None = None
    stage: str | None = None
    status: DecisionStatus = "confirmed"
    alternatives: list[DecisionAlternative] = field(default_factory=list)
    reasons: list[DecisionReason] = field(default_factory=list)
    participants: list[str] = field(default_factory=list)
    source_event_id: str | None = None
    source_type: str = "feishu_chat"
    source_ref: str | None = None
    decided_at: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    tags: list[str] = field(default_factory=list)
    confidence: float = 0.5
    importance: float = 0.5
    overwrite_of: str | None = None
    superseded_by: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_memory_core(self) -> MemoryCore:
        scope = "project" if self.project_id else "team" if self.team_id else "workspace"
        entities = _unique(
            [
                *( [f"project_id:{self.project_id}", self.project_id] if self.project_id else [] ),
                *( [f"workspace_id:{self.workspace_id}", self.workspace_id] if self.workspace_id else [] ),
                *( [f"team_id:{self.team_id}", self.team_id] if self.team_id else [] ),
                *( [f"thread_id:{self.thread_id}", self.thread_id] if self.thread_id else [] ),
                f"topic:{self.topic}",
                self.topic,
                *[f"participant:{participant}" for participant in self.participants],
                *self.participants,
            ]
        )
        tags = _unique(
            [
                "project_decision",
                f"status:{self.status}",
                *( [f"stage:{self.stage}", self.stage] if self.stage else [] ),
                *[f"alternative:{alternative.name}" for alternative in self.alternatives],
                *[alternative.name for alternative in self.alternatives],
                *self.tags,
            ]
        )
        now = utc_now_iso()
        return MemoryCore(
            memory_id=self.decision_id,
            domain="project_decision",
            memory_type="project_decision",
            scope=scope,  # type: ignore[arg-type]
            source_type=self.source_type,
            source_ref=self.source_ref or self.thread_id or self.project_id or "unknown",
            source_event_id=self.source_event_id,
            content_text=self.build_content_text(),
            summary_text=self.build_summary_text(),
            entities=entities,
            tags=tags,
            importance=_clamp(self.importance),
            confidence=_clamp(self.confidence),
            status="superseded" if self.status == "superseded" else "active",
            valid_from=self.valid_from or self.decided_at,
            valid_to=self.valid_to,
            overwrite_of=self.overwrite_of,
            superseded_by=self.superseded_by,
            created_at=self.decided_at or now,
            updated_at=now,
        )

    def build_content_text(self) -> str:
        lines = [
            f"项目决策: {self.topic}",
            f"结论: {self.decision}",
        ]
        if self.conclusion and self.conclusion != self.decision:
            lines.append(f"完整结论: {self.conclusion}")
        if self.stage:
            lines.append(f"阶段: {self.stage}")
        if self.status:
            lines.append(f"状态: {self.status}")
        support = [reason.text for reason in self.reasons if reason.reason_type in {"support", "context"}]
        against = [reason.text for reason in self.reasons if reason.reason_type in {"against", "risk"}]
        constraints = [reason.text for reason in self.reasons if reason.reason_type == "constraint"]
        if support:
            lines.append("理由: " + "；".join(support))
        if against:
            lines.append("反对意见: " + "；".join(against))
        if constraints:
            lines.append("约束: " + "；".join(constraints))
        if self.alternatives:
            parts = [
                f"{alternative.name}({alternative.status})"
                for alternative in self.alternatives
                if alternative.name
            ]
            lines.append("备选方案: " + "；".join(parts))
        if self.decided_at:
            lines.append(f"决策时间: {self.decided_at}")
        if self.source_ref:
            lines.append(f"来源: {self.source_ref}")
        return "\n".join(line for line in lines if line.strip())

    def build_summary_text(self) -> str:
        stage = f"[{self.stage}] " if self.stage else ""
        summary = f"{stage}{self.topic}: {self.decision}"
        return truncate_text(clean_text(summary), 200)

    def to_card(self) -> dict[str, Any]:
        return {
            "type": "project_decision_card",
            "title": f"历史决策: {self.topic}",
            "topic": self.topic,
            "decision": self.decision,
            "stage": self.stage,
            "decided_at": self.decided_at,
            "reasons": [reason.to_dict() for reason in self.reasons],
            "alternatives": [alternative.to_dict() for alternative in self.alternatives],
            "source_ref": self.source_ref,
            "confidence": _clamp(self.confidence),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "project_id": self.project_id,
            "workspace_id": self.workspace_id,
            "team_id": self.team_id,
            "thread_id": self.thread_id,
            "topic": self.topic,
            "decision": self.decision,
            "conclusion": self.conclusion,
            "stage": self.stage,
            "status": self.status,
            "alternatives": [alternative.to_dict() for alternative in self.alternatives],
            "reasons": [reason.to_dict() for reason in self.reasons],
            "participants": list(self.participants),
            "source_event_id": self.source_event_id,
            "source_type": self.source_type,
            "source_ref": self.source_ref,
            "decided_at": self.decided_at,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "tags": list(self.tags),
            "confidence": _clamp(self.confidence),
            "importance": _clamp(self.importance),
            "overwrite_of": self.overwrite_of,
            "superseded_by": self.superseded_by,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_memory_core(cls, memory: MemoryCore | dict[str, Any]) -> ProjectDecision:
        data = memory if isinstance(memory, dict) else {
            name: getattr(memory, name)
            for name in MemoryCore.__dataclass_fields__
            if hasattr(memory, name)
        }
        entities = list(data.get("entities") or data.get("entities_json") or [])
        tags = list(data.get("tags") or data.get("tags_json") or [])
        content = str(data.get("content_text") or "")
        summary = data.get("summary_text") or ""
        extra = data.get("extra") or {}
        project_id = extra.get("project_id") or _field_from_entities(entities, "project_id")
        workspace_id = extra.get("workspace_id") or _field_from_entities(entities, "workspace_id")
        team_id = extra.get("team_id") or _field_from_entities(entities, "team_id")
        thread_id = extra.get("thread_id") or _field_from_entities(entities, "thread_id")
        topic = extra.get("topic") or _field_from_entities(entities, "topic") or _line_value(content, "项目决策")
        decision = extra.get("decision") or _line_value(content, "结论")
        if not topic and ":" in summary:
            topic = summary.split(":", 1)[0].strip()
        if not decision and ":" in summary:
            decision = summary.split(":", 1)[1].strip()
        stage = extra.get("stage") or _line_value(content, "阶段")
        if not stage:
            for tag in tags:
                if tag.startswith("stage:"):
                    stage = tag.split(":", 1)[1]
                    break
        status: DecisionStatus = "confirmed"
        if data.get("status") == "superseded":
            status = "superseded"
        else:
            for tag in tags:
                if tag.startswith("status:"):
                    status = tag.split(":", 1)[1]  # type: ignore[assignment]
                    break
        alternatives = [
            DecisionAlternative(name=tag.split(":", 1)[1])
            for tag in tags
            if tag.startswith("alternative:") and tag.split(":", 1)[1]
        ]
        decided_at = data.get("valid_from") or data.get("created_at")
        return cls(
            decision_id=str(data.get("memory_id")),
            project_id=project_id,
            workspace_id=workspace_id,
            team_id=team_id,
            thread_id=thread_id,
            topic=topic or clean_text(summary) or "未命名决策",
            decision=decision or clean_text(content) or clean_text(summary),
            stage=stage,
            status=status,
            alternatives=alternatives,
            source_event_id=data.get("source_event_id"),
            source_type=str(data.get("source_type") or "feishu_chat"),
            source_ref=data.get("source_ref"),
            decided_at=decided_at,
            valid_from=data.get("valid_from"),
            valid_to=data.get("valid_to"),
            tags=[tag for tag in tags if not tag.startswith(("stage:", "status:", "alternative:"))],
            confidence=float(data.get("confidence") or 0.0),
            importance=float(data.get("importance") or 0.0),
            overwrite_of=data.get("overwrite_of"),
            superseded_by=data.get("superseded_by"),
        )


@dataclass(slots=True)
class ProjectDecisionCandidate:
    """A project decision extracted from source text before admission."""

    decision: ProjectDecision
    evidence_text: str
    signals: list[str] = field(default_factory=list)
    needs_review: bool = False

    def is_admissible(self, min_confidence: float = 0.45) -> bool:
        if not clean_text(self.decision.topic) or not clean_text(self.decision.decision):
            return False
        if self.decision.confidence < min_confidence:
            return False
        if self.decision.status == "unknown" and not self.signals:
            return False
        return True

