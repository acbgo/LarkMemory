"""Retrieval 包内共享的数据模型。

后续与 schemas/ 统一模型对齐时，这里的定义将作为检索层视图保留，
或迁移到 schemas/retrieve.py 与 schemas/memory_core.py。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class MemoryDomain(str, Enum):
    CLI_WORKFLOW = "cli_workflow"
    PROJECT_DECISION = "project_decision"
    PERSONAL_PREFERENCE = "personal_preference"
    TEAM_RETENTION = "team_retention"


class MemoryScope(str, Enum):
    USER = "user"
    PROJECT = "project"
    TEAM = "team"
    WORKSPACE = "workspace"
    GLOBAL = "global"


MemoryStatus = Literal[
    "active", "candidate", "superseded", "expired", "forgotten"
]


# ---------------------------------------------------------------------------
# 记忆项（检索视图）
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class MemoryItem:
    """从存储层加载后用于检索排序的记忆快照。"""

    memory_id: str
    domain: MemoryDomain
    memory_type: str
    content_text: str
    importance: float = 0.5
    confidence: float = 0.5
    status: MemoryStatus = "active"

    scope: MemoryScope = MemoryScope.USER
    summary_text: str | None = None
    freshness_score: float | None = None
    tags: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    source_ref: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    # 领域专属扩展字段（由各 domain retriever 填充）
    extra: dict[str, Any] = field(default_factory=dict)


_MEMORY_CORE_FIELDS = {
    "memory_id",
    "domain",
    "memory_type",
    "scope",
    "source_type",
    "source_ref",
    "source_event_id",
    "content_text",
    "summary_text",
    "entities",
    "entities_json",
    "tags",
    "tags_json",
    "importance",
    "confidence",
    "freshness_score",
    "status",
    "valid_from",
    "valid_to",
    "overwrite_of",
    "superseded_by",
    "trigger_policy_id",
    "decay_policy_id",
    "embedding_id",
    "created_at",
    "updated_at",
}


def memory_item_from_core(
    memory: Any,
    *,
    extra: dict[str, Any] | None = None,
) -> MemoryItem:
    """将 schemas.MemoryCore 或 MemoryCoreStore row 转为检索层 MemoryItem。"""
    data = memory if isinstance(memory, dict) else {
        name: getattr(memory, name)
        for name in _MEMORY_CORE_FIELDS
        if hasattr(memory, name)
    }

    item_extra = {
        key: value
        for key, value in data.items()
        if key not in _MEMORY_CORE_FIELDS and value is not None
    }
    for key in (
        "source_type",
        "source_event_id",
        "valid_from",
        "valid_to",
        "overwrite_of",
        "superseded_by",
        "trigger_policy_id",
        "decay_policy_id",
        "embedding_id",
    ):
        value = data.get(key)
        if value is not None:
            item_extra[key] = value
    if extra:
        item_extra.update(extra)

    entities = data.get("entities")
    if entities is None:
        entities = data.get("entities_json") or []
    tags = data.get("tags")
    if tags is None:
        tags = data.get("tags_json") or []

    return MemoryItem(
        memory_id=str(data["memory_id"]),
        domain=MemoryDomain(data["domain"]),
        memory_type=str(data["memory_type"]),
        content_text=str(data["content_text"]),
        importance=float(data.get("importance", 0.5) or 0.0),
        confidence=float(data.get("confidence", 0.5) or 0.0),
        status=data.get("status", "active"),
        scope=MemoryScope(data.get("scope", MemoryScope.USER.value)),
        summary_text=data.get("summary_text"),
        freshness_score=data.get("freshness_score"),
        tags=list(tags),
        entities=list(entities),
        source_ref=data.get("source_ref"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        extra=item_extra,
    )


# ---------------------------------------------------------------------------
# 检索请求
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class RetrievalQuery:
    """外部传入的检索请求。"""

    query_text: str
    user_id: str | None = None
    project_id: str | None = None
    repo_id: str | None = None
    workspace_id: str | None = None
    team_id: str | None = None
    session_context: dict[str, Any] = field(default_factory=dict)
    timestamp: str | None = None


# ---------------------------------------------------------------------------
# 意图分析输出
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class IntentResult:
    """IntentAnalyzer 的输出。"""

    primary_domains: list[MemoryDomain]
    secondary_domains: list[MemoryDomain] = field(default_factory=list)
    intent_type: str = "general"
    keywords: list[str] = field(default_factory=list)
    time_hint: str | None = None
    confidence: float = 0.5


# ---------------------------------------------------------------------------
# 查询改写输出
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class TimeWindow:
    start: str | None = None
    end: str | None = None
    description: str | None = None


@dataclass(slots=True)
class RewrittenQuery:
    """QueryRewriter 的输出。"""

    original: RetrievalQuery
    rewritten_text: str = ""
    query_variants: list[str] = field(default_factory=list)
    extracted_topics: list[str] = field(default_factory=list)
    time_window: TimeWindow | None = None
    scope_filters: dict[str, str] = field(default_factory=dict)
    boost_signals: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 领域召回结果
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class DomainRecallResult:
    """单个领域 retriever 返回的召回结果。"""

    domain: MemoryDomain
    items: list[MemoryItem] = field(default_factory=list)
    recall_method: str = "default"
    latency_ms: float = 0.0


# ---------------------------------------------------------------------------
# 融合候选
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class FusedCandidate:
    """经过跨域融合后的候选记忆项。"""

    item: MemoryItem
    source_domain: MemoryDomain
    domain_rank: int = 0
    fusion_score: float = 0.0


# ---------------------------------------------------------------------------
# 最终排序结果
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class RankedMemory:
    """Reranker 输出的最终排序结果。"""

    item: MemoryItem
    final_score: float = 0.0
    score_breakdown: dict[str, float] = field(default_factory=dict)
    rank: int = 0


# ---------------------------------------------------------------------------
# 链路追踪
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class TraceStep:
    """检索管线中单个步骤的追踪记录。"""

    name: str
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: float = 0.0
    input_summary: dict[str, Any] = field(default_factory=dict)
    output_summary: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    children: list[TraceStep] = field(default_factory=list)


@dataclass(slots=True)
class RetrievalTrace:
    """一次完整检索的链路追踪。"""

    query_id: str
    start_time: float = 0.0
    end_time: float = 0.0
    total_duration_ms: float = 0.0
    steps: list[TraceStep] = field(default_factory=list)
    final_result_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
