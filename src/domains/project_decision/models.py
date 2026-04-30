from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from src.schemas import MemoryCore
from src.utils.ids import memory_id
from src.utils.text import clean_text, truncate_text
from src.utils.time import utc_now_iso


logger = logging.getLogger(__name__)


DecisionStatus = Literal["confirmed", "superseded"]


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


def _line_list(text: str, label: str) -> list[str]:
    value = _line_value(text, label)
    if not value:
        return []
    return _unique([part.strip() for part in value.split("；")])


@dataclass(slots=True)
class ProjectDecision:
    """历史决策卡片模型，服务决策抽取、召回和主动推送。"""

    # 决策记忆的唯一 ID，同时作为写入 MemoryCore 的 memory_id。
    decision_id: str = field(default_factory=memory_id)
    # 飞书项目或业务项目 ID，用于限定召回范围。
    project_id: str | None = None
    # 飞书工作区 ID，用于项目缺失时的上层范围过滤。
    workspace_id: str | None = None
    # 飞书群聊或团队 ID，用于群聊维度的范围过滤。
    team_id: str | None = None
    # 飞书消息线程或文档讨论串 ID，用于回溯原始讨论上下文。
    thread_id: str | None = None
    # 决策主题，例如“数据库选型”或“截止日期”。
    topic: str = ""
    # 最终采用的决策内容，例如“采用方案 B”。
    decision: str = ""
    # 更完整的结论说明；为空时默认使用 decision。
    conclusion: str | None = None
    # 支持该决策的理由列表。
    reasons: list[str] = field(default_factory=list)
    # 反对意见、风险或保留意见列表。
    objections: list[str] = field(default_factory=list)
    # 被讨论过的备选方案名称，例如“方案 A”“方案 B”。
    alternatives: list[str] = field(default_factory=list)
    # 项目阶段，例如“技术选型”“上线前”。
    stage: str | None = None
    # 决策发生或被确认的时间点。
    decided_at: str | None = None
    # 原始事件 ID，用于回链到 ingest event。
    source_event_id: str | None = None
    # 来源类型，例如 feishu_chat、feishu_doc。
    source_type: str = "feishu_chat"
    # 来源引用，例如 message_id、doc_id 或 thread_id。
    source_ref: str | None = None
    # 当前决策状态；只保留活跃确认态和被覆盖态。
    status: DecisionStatus = "confirmed"
    # 模型或规则抽取置信度，范围 0 到 1。
    confidence: float = 0.5
    # 记忆重要性，影响排序和长期保留，范围 0 到 1。
    importance: float = 0.5
    # 当前决策覆盖的旧决策 ID。
    overwrite_of: str | None = None
    # 当前决策被哪个新决策覆盖。
    superseded_by: str | None = None
    # 预留扩展字段，存放非主链路需要的附加信息。
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_memory_core(self) -> MemoryCore:
        """将历史决策卡片转换为统一 MemoryCore 结构。"""

        logger.info(
            "action=start decision_id=%s topic=%s status=%s",
            self.decision_id,
            self.topic,
            self.status,
        )
        scope = "project" if self.project_id else "team" if self.team_id else "workspace"
        entities = _unique(
            [
                *( [f"project_id:{self.project_id}", self.project_id] if self.project_id else [] ),
                *( [f"workspace_id:{self.workspace_id}", self.workspace_id] if self.workspace_id else [] ),
                *( [f"team_id:{self.team_id}", self.team_id] if self.team_id else [] ),
                *( [f"thread_id:{self.thread_id}", self.thread_id] if self.thread_id else [] ),
                f"topic:{self.topic}",
                self.topic,
            ]
        )
        tags = _unique(
            [
                "project_decision",
                f"status:{self.status}",
                *( [f"stage:{self.stage}", self.stage] if self.stage else [] ),
                *[f"alternative:{alternative}" for alternative in self.alternatives],
                *self.alternatives,
            ]
        )
        now = utc_now_iso()
        memory = MemoryCore(
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
            valid_from=self.decided_at,
            overwrite_of=self.overwrite_of,
            superseded_by=self.superseded_by,
            created_at=self.decided_at or now,
            updated_at=now,
        )
        logger.info(
            "action=done decision_id=%s memory_id=%s scope=%s entity_count=%s tag_count=%s",
            self.decision_id,
            memory.memory_id,
            memory.scope,
            len(memory.entities),
            len(memory.tags),
        )
        return memory

    def build_content_text(self) -> str:
        """构造可检索、可展示的决策正文。"""

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
        if self.reasons:
            lines.append("理由: " + "；".join(_unique(self.reasons)))
        if self.objections:
            lines.append("反对意见: " + "；".join(_unique(self.objections)))
        if self.alternatives:
            lines.append("备选方案: " + "；".join(_unique(self.alternatives)))
        if self.decided_at:
            lines.append(f"决策时间: {self.decided_at}")
        if self.source_ref:
            lines.append(f"来源: {self.source_ref}")
        return "\n".join(line for line in lines if line.strip())

    def build_summary_text(self) -> str:
        """构造用于列表和检索排序的短摘要。"""

        stage = f"[{self.stage}] " if self.stage else ""
        summary = f"{stage}{self.topic}: {self.decision}"
        return truncate_text(clean_text(summary), 200)

    def to_card(self) -> dict[str, Any]:
        """输出历史决策卡片所需的最小字段。"""

        return {
            "type": "project_decision_card",
            "title": f"历史决策: {self.topic}",
            "topic": self.topic,
            "decision": self.decision,
            "conclusion": self.conclusion,
            "reasons": list(self.reasons),
            "objections": list(self.objections),
            "alternatives": list(self.alternatives),
            "stage": self.stage,
            "decided_at": self.decided_at,
            "source_ref": self.source_ref,
            "confidence": _clamp(self.confidence),
        }

    def to_dict(self) -> dict[str, Any]:
        """输出便于测试、调试和后续持久化的字典结构。"""

        return {
            "decision_id": self.decision_id,
            "project_id": self.project_id,
            "workspace_id": self.workspace_id,
            "team_id": self.team_id,
            "thread_id": self.thread_id,
            "topic": self.topic,
            "decision": self.decision,
            "conclusion": self.conclusion,
            "reasons": list(self.reasons),
            "objections": list(self.objections),
            "alternatives": list(self.alternatives),
            "stage": self.stage,
            "decided_at": self.decided_at,
            "source_event_id": self.source_event_id,
            "source_type": self.source_type,
            "source_ref": self.source_ref,
            "status": self.status,
            "confidence": _clamp(self.confidence),
            "importance": _clamp(self.importance),
            "overwrite_of": self.overwrite_of,
            "superseded_by": self.superseded_by,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_memory_core(cls, memory: MemoryCore | dict[str, Any]) -> ProjectDecision:
        """从 MemoryCore 行恢复历史决策卡片模型。"""

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
        status: DecisionStatus = "superseded" if data.get("status") == "superseded" else "confirmed"
        alternatives = [
            tag.split(":", 1)[1]
            for tag in tags
            if tag.startswith("alternative:") and tag.split(":", 1)[1]
        ]
        return cls(
            decision_id=str(data.get("memory_id")),
            project_id=project_id,
            workspace_id=workspace_id,
            team_id=team_id,
            thread_id=thread_id,
            topic=topic or clean_text(summary) or "未命名决策",
            decision=decision or clean_text(content) or clean_text(summary),
            conclusion=_line_value(content, "完整结论"),
            reasons=_line_list(content, "理由"),
            objections=_line_list(content, "反对意见"),
            alternatives=_unique(alternatives or _line_list(content, "备选方案")),
            stage=stage,
            decided_at=data.get("valid_from") or data.get("created_at"),
            source_event_id=data.get("source_event_id"),
            source_type=str(data.get("source_type") or "feishu_chat"),
            source_ref=data.get("source_ref"),
            status=status,
            confidence=float(data.get("confidence") or 0.0),
            importance=float(data.get("importance") or 0.0),
            overwrite_of=data.get("overwrite_of"),
            superseded_by=data.get("superseded_by"),
        )


@dataclass(slots=True)
class ProjectDecisionCandidate:
    """抽取出的候选决策，进入 MemoryCore 前先做准入判断。"""

    # 候选决策卡片本体。
    decision: ProjectDecision
    # 支撑该候选的原文片段。
    evidence_text: str
    # 抽取命中的信号，例如关键词或 LLM 来源。
    signals: list[str] = field(default_factory=list)
    # 是否需要人工复核。
    needs_review: bool = False

    def is_admissible(self, min_confidence: float = 0.45) -> bool:
        """判断候选决策是否满足最小入库条件。"""

        if not clean_text(self.decision.topic) or not clean_text(self.decision.decision):
            return False
        if self.decision.confidence < min_confidence:
            return False
        return True
