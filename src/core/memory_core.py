from __future__ import annotations

from dataclasses import replace

from src.schemas import MemoryCore
from src.utils.ids import memory_id as new_memory_id
from src.utils.text import clean_text
from src.utils.time import utc_now_iso


ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "candidate": {"active", "forgotten", "expired"},
    "active": {"superseded", "expired", "forgotten"},
    "superseded": {"forgotten"},
    "expired": {"active", "forgotten"},
    "forgotten": set(),
}


class MemoryLifecycle:
    def can_transition(self, from_status: str, to_status: str) -> bool:
        if from_status == to_status:
            return from_status in ALLOWED_STATUS_TRANSITIONS
        return to_status in ALLOWED_STATUS_TRANSITIONS.get(from_status, set())

    def validate_transition(self, from_status: str, to_status: str) -> None:
        if not self.can_transition(from_status, to_status):
            raise ValueError(f"invalid memory status transition: {from_status} -> {to_status}")

    def transition(
        self,
        memory: MemoryCore,
        to_status: str,
        *,
        updated_at: str | None = None,
    ) -> MemoryCore:
        self.validate_transition(memory.status, to_status)
        return replace(memory, status=to_status, updated_at=updated_at or utc_now_iso())


def clamp_score(value: float, *, name: str = "score") -> float:
    if value < 0.0 or value > 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")
    return float(value)


def create_memory_core(
    *,
    domain: str,
    memory_type: str,
    scope: str,
    source_type: str,
    source_ref: str,
    content_text: str,
    memory_id: str | None = None,
    source_event_id: str | None = None,
    summary_text: str | None = None,
    entities: list[str] | None = None,
    tags: list[str] | None = None,
    importance: float = 0.5,
    confidence: float = 0.5,
    status: str = "candidate",
    created_at: str | None = None,
    updated_at: str | None = None,
) -> MemoryCore:
    cleaned = clean_text(content_text)
    if not cleaned:
        raise ValueError("content_text cannot be empty")
    now = utc_now_iso()
    created = created_at or now
    updated = updated_at or created
    return MemoryCore(
        memory_id=memory_id or new_memory_id(),
        domain=domain,  # type: ignore[arg-type]
        memory_type=memory_type,
        scope=scope,  # type: ignore[arg-type]
        source_type=source_type,
        source_ref=source_ref,
        source_event_id=source_event_id,
        content_text=cleaned,
        summary_text=summary_text,
        entities=entities or [],
        tags=tags or [],
        importance=clamp_score(importance, name="importance"),
        confidence=clamp_score(confidence, name="confidence"),
        status=status,  # type: ignore[arg-type]
        created_at=created,
        updated_at=updated,
    )
