from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.core.decay import DecayPolicy
from src.storage import MemoryCoreStore


@dataclass(slots=True)
class ScheduledTaskResult:
    task_name: str
    scanned: int = 0
    updated: int = 0
    suggestions: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class Scheduler:
    def __init__(
        self,
        memory_store: MemoryCoreStore,
        decay_policy: DecayPolicy | None = None,
    ) -> None:
        self.memory_store = memory_store
        self.decay_policy = decay_policy or DecayPolicy()

    def scan_decay(
        self,
        *,
        domain: str | None = None,
        limit: int = 500,
    ) -> ScheduledTaskResult:
        result = ScheduledTaskResult(task_name="decay")
        rows = self.memory_store.list_active_memories(domain=domain, limit=limit)
        for row in rows:
            result.scanned += 1
            try:
                decision = self.decay_policy.apply(self.memory_store, row)
                if decision.new_status is not None:
                    result.updated += 1
            except Exception as exc:
                result.errors.append(str(exc))
        return result

    def scan_review_due(
        self,
        *,
        limit: int = 100,
        now: str | None = None,
        warning_window_hours: int = 24,
    ) -> ScheduledTaskResult:
        del limit, now, warning_window_hours
        return ScheduledTaskResult(task_name="review_due")

    def run_once(self) -> dict[str, ScheduledTaskResult]:
        decay = self.scan_decay()
        review = self.scan_review_due()
        return {
            decay.task_name: decay,
            review.task_name: review,
        }
