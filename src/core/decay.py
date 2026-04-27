from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from src.core.dedup_merge import memory_from_row
from src.schemas import MemoryCore
from src.storage import MemoryCoreStore
from src.utils.time import days_between, parse_iso, utc_now_iso


@dataclass(slots=True)
class DecayDecision:
    memory_id: str
    new_status: str | None = None
    freshness_score: float | None = None
    should_update: bool = False
    reason: str = ""


class DecayPolicy:
    def __init__(
        self,
        half_life_days_by_domain: dict[str, float] | None = None,
        expire_after_days_by_domain: dict[str, float] | None = None,
    ) -> None:
        self.half_life_days_by_domain = {
            "cli_workflow": 30.0,
            "project_decision": 180.0,
            "personal_preference": 90.0,
            "team_retention": 365.0,
            **(half_life_days_by_domain or {}),
        }
        self.expire_after_days_by_domain = {
            "cli_workflow": 180.0,
            **(expire_after_days_by_domain or {}),
        }

    def freshness(self, updated_at: str | None, *, domain: str, now: str | None = None) -> float:
        if not updated_at:
            return 0.3
        current = now or utc_now_iso()
        age_days = max(days_between(updated_at, current), 0.0)
        half_life = self.half_life_days_by_domain.get(domain, 180.0)
        if half_life <= 0:
            return 0.0
        return max(min(math.exp(-0.693 * age_days / half_life), 1.0), 0.0)

    def evaluate(
        self,
        memory: MemoryCore | dict[str, Any],
        *,
        now: str | None = None,
    ) -> DecayDecision:
        item = memory_from_row(memory)
        if item.status in {"expired", "forgotten"}:
            return DecayDecision(item.memory_id, reason="terminal status")
        current = now or utc_now_iso()
        updated_at = item.updated_at or item.created_at
        freshness_score = self.freshness(updated_at, domain=item.domain, now=current)
        expire_after = self.expire_after_days_by_domain.get(item.domain)
        if expire_after is not None and updated_at:
            age_days = max(days_between(updated_at, current), 0.0)
            if age_days > expire_after:
                return DecayDecision(
                    item.memory_id,
                    new_status="expired",
                    freshness_score=freshness_score,
                    should_update=True,
                    reason="expired by decay policy",
                )
        return DecayDecision(
            item.memory_id,
            freshness_score=freshness_score,
            should_update=True,
            reason="freshness calculated",
        )

    def apply(
        self,
        memory_store: MemoryCoreStore,
        memory: MemoryCore | dict[str, Any],
        *,
        now: str | None = None,
    ) -> DecayDecision:
        decision = self.evaluate(memory, now=now)
        if decision.new_status is not None:
            memory_store.update_memory_status(decision.memory_id, decision.new_status)
        return decision
