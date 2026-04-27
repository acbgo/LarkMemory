from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.core.decay import DecayPolicy
from src.storage import MemoryCoreStore, TeamRetentionStore


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
        team_retention_store: TeamRetentionStore | None = None,
    ) -> None:
        self.memory_store = memory_store
        self.decay_policy = decay_policy or DecayPolicy()
        self.team_retention_store = team_retention_store

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
        result = ScheduledTaskResult(task_name="review_due")
        if self.team_retention_store is None:
            return result
        schedules = self.team_retention_store.list_due_reviews(
            now=now,
            warning_window_hours=warning_window_hours,
            limit=limit,
        )
        memory_rows = {
            row["memory_id"]: row
            for row in self.memory_store.batch_get_memories([item.memory_id for item in schedules])
            if row.get("status") == "active" and row.get("domain") == "team_retention"
        }
        for schedule in schedules:
            result.scanned += 1
            row = memory_rows.get(schedule.memory_id)
            if row is None:
                continue
            memory = self.team_retention_store.get_memory(schedule.memory_id)
            if memory is None:
                continue
            result.suggestions.append(
                {
                    "type": "review_reminder",
                    "memory_id": schedule.memory_id,
                    "due_at": schedule.next_review_at,
                    "content": memory.fact_value,
                    "metadata": {
                        "domain": "team_retention",
                        "fact_type": memory.fact_type,
                        "risk_level": memory.risk_level,
                        "team_id": memory.team_id,
                        "project_id": memory.project_id,
                        "review_count": schedule.review_count,
                    },
                }
            )
        return result

    def run_once(self) -> dict[str, ScheduledTaskResult]:
        decay = self.scan_decay()
        review = self.scan_review_due()
        return {
            decay.task_name: decay,
            review.task_name: review,
        }
