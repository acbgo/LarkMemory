from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(slots=True)
class RerankDocument:
    """Document submitted to a rerank model."""

    id: str
    text: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class RerankScore:
    """Score returned by a rerank provider for an input document index."""

    index: int
    score: float


@dataclass(slots=True)
class RerankResult:
    """Ranked document returned to API consumers."""

    id: str
    text: str
    score: float
    rank: int
    index: int
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class RerankResponse:
    """Rerank response shared by API and provider callers."""

    model: str
    results: list[RerankResult]


class RerankProvider(Protocol):
    """Provider contract for rerank model services."""

    def score(self, query: str, documents: list[str]) -> list[RerankScore]:
        """Return relevance scores for documents in the original input index space."""
        ...
