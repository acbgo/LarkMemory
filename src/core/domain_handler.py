from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from src.retrieval import RankedMemory, RetrievalQuery
from src.schemas import MemoryCore, NormalizedEvent
from src.storage import MemoryCoreStore


@dataclass(slots=True)
class DomainIngestResult:
    memory_ids: list[str] = field(default_factory=list)
    candidate_count: int = 0
    message: str | None = None


@dataclass(slots=True)
class DomainUpdateResult:
    action: str
    memory_id: str | None = None
    updated: bool = False
    message: str | None = None


@dataclass(slots=True)
class DomainRuntime:
    memory_store: MemoryCoreStore
    add_memory: Callable[[MemoryCore], str]


class MemoryDomainHandler(Protocol):
    domain: str

    def ingest_event(self, event: NormalizedEvent, runtime: DomainRuntime) -> DomainIngestResult:
        ...

    def retrieve(self, query: RetrievalQuery, *, top_k: int) -> list[RankedMemory]:
        ...

    def update_memory(self, action: str, **kwargs: Any) -> DomainUpdateResult | None:
        ...

    def proactive_suggestions(self, **kwargs: Any) -> list[dict[str, Any]]:
        ...

    def scan_review_due(self, **kwargs: Any) -> list[dict[str, Any]]:
        ...
