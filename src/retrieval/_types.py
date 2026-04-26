"""Retrieval 包内共享的数据模型。

后续与 schemas/ 统一模型对齐时，这里的定义将作为检索层视图保留，
或迁移到 schemas/retrieve.py 与 schemas/memory_core.py。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
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
