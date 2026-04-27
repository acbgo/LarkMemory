from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.utils.ids import new_id
from src.utils.time import utc_now_iso


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AccessRecord:
    access_id: str
    memory_id: str
    access_type: str
    query_id: str | None = None
    agent_session_id: str | None = None
    used_in_response: bool = False
    feedback_signal: str | None = None
    accessed_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class AccessTracker:
    def __init__(
        self,
        persist_fn: Callable[[AccessRecord], None] | None = None,
        max_recent: int = 200,
    ) -> None:
        self.persist_fn = persist_fn
        self._recent: deque[AccessRecord] = deque(maxlen=max_recent)

    def record_access(
        self,
        memory_id: str,
        *,
        access_type: str = "retrieved",
        query_id: str | None = None,
        agent_session_id: str | None = None,
        used_in_response: bool = False,
        feedback_signal: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AccessRecord:
        record = AccessRecord(
            access_id=new_id("acc"),
            memory_id=memory_id,
            access_type=access_type,
            query_id=query_id,
            agent_session_id=agent_session_id,
            used_in_response=used_in_response,
            feedback_signal=feedback_signal,
            accessed_at=utc_now_iso(),
            metadata=metadata or {},
        )
        self._recent.append(record)
        if self.persist_fn is not None:
            try:
                self.persist_fn(record)
            except Exception:
                logger.warning("failed to persist access record", exc_info=True)
        return record

    def record_feedback(
        self,
        memory_id: str,
        feedback_signal: str,
        *,
        query_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AccessRecord:
        return self.record_access(
            memory_id,
            access_type="feedback",
            query_id=query_id,
            feedback_signal=feedback_signal,
            metadata=metadata,
        )

    def recent_records(self) -> list[AccessRecord]:
        return list(self._recent)

    def stats_by_memory(self) -> dict[str, dict[str, int]]:
        stats: dict[str, dict[str, int]] = {}
        for record in self._recent:
            memory_stats = stats.setdefault(record.memory_id, {})
            memory_stats[record.access_type] = memory_stats.get(record.access_type, 0) + 1
        return stats
