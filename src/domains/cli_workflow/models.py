from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from src.schemas import MemoryCore
from src.utils.ids import memory_id
from src.utils.text import clean_text, truncate_text
from src.utils.time import utc_now_iso


logger = logging.getLogger(__name__)

WorkflowStatus = Literal["active", "superseded"]


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


def _param_tags_to_bindings(tags: list[str]) -> list[ParameterBinding]:
    bindings: dict[tuple[str, str], ParameterBinding] = {}
    for tag in tags:
        if tag.startswith("param:"):
            inner = tag[len("param:"):]
            if "=" not in inner:
                continue
            name, value = inner.split("=", 1)
            if not name or not value:
                continue
            key = (name, value)
            if key in bindings:
                bindings[key].frequency += 1
            else:
                bindings[key] = ParameterBinding(param_name=name, param_value=value, frequency=1)
    return list(bindings.values())


@dataclass(slots=True)
class ParameterBinding:
    """单个参数与其在当前上下文中的取值记录。"""

    param_name: str
    param_value: str
    frequency: int = 1
    semantics: str | None = None


@dataclass(slots=True)
class CLIWorkflowMemory:
    """CLI 工作流记忆 — 一条参数化的命令模板及其在项目中的参数习惯。"""

    workflow_id: str = field(default_factory=memory_id)
    user_id: str = ""
    command_template: str = ""
    command_name: str = ""
    command_category: str = "general"
    project_id: str | None = None
    repo_id: str | None = None
    semantic_description: str | None = None
    scenario_keywords: list[str] = field(default_factory=list)
    parameter_bindings: list[ParameterBinding] = field(default_factory=list)
    execution_count: int = 1
    last_executed_at: str | None = None
    success_count: int = 0
    source_type: str = "shell"
    source_event_id: str | None = None
    status: WorkflowStatus = "active"
    overwrite_of: str | None = None
    superseded_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @property
    def success_rate(self) -> float:
        if self.execution_count <= 0:
            return 0.0
        return _clamp(self.success_count / self.execution_count)

    def to_memory_core(self) -> MemoryCore:
        logger.info(
            "action=start workflow_id=%s command_name=%s project_id=%s",
            self.workflow_id,
            self.command_name,
            self.project_id,
        )
        entities = _unique(
            [
                f"user_id:{self.user_id}",
                *( [f"project_id:{self.project_id}"] if self.project_id else [] ),
                *( [f"repo_id:{self.repo_id}"] if self.repo_id else [] ),
                f"command_name:{self.command_name}",
                f"command_template:{self.command_template}",
                *[f"scenario:{keyword}" for keyword in self.scenario_keywords],
            ]
        )
        tags = _unique(
            [
                "cli_workflow",
                f"category:{self.command_category}",
                f"source:{self.source_type}",
                *[f"param:{pb.param_name}={pb.param_value}" for pb in self.parameter_bindings],
            ]
        )
        now = utc_now_iso()
        memory = MemoryCore(
            memory_id=self.workflow_id,
            domain="cli_workflow",
            memory_type="cli_workflow",
            scope="user",
            source_type=self.source_type,
            source_ref=self.project_id or self.repo_id or "unknown",
            source_event_id=self.source_event_id,
            content_text=self.build_content_text(),
            summary_text=self.build_summary_text(),
            entities=entities,
            tags=tags,
            importance=self._execution_importance(),
            confidence=self.success_rate,
            freshness_score=self._freshness(),
            status="superseded" if self.status == "superseded" else "active",
            overwrite_of=self.overwrite_of,
            superseded_by=self.superseded_by,
            created_at=self.created_at or now,
            updated_at=now,
        )
        logger.info(
            "action=done workflow_id=%s memory_id=%s execution_count=%s",
            self.workflow_id,
            memory.memory_id,
            self.execution_count,
        )
        return memory

    def build_content_text(self) -> str:
        lines = [
            f"命令模板: {self.command_template}",
            f"命令: {self.command_name}",
            f"分类: {self.command_category}",
        ]
        if self.project_id:
            lines.append(f"项目: {self.project_id}")
        if self.repo_id:
            lines.append(f"仓库: {self.repo_id}")
        if self.semantic_description:
            lines.append(f"语义: {self.semantic_description}")
        if self.scenario_keywords:
            lines.append(f"场景关键词: {', '.join(self.scenario_keywords)}")
        lines.append(f"执行次数: {self.execution_count}")
        lines.append(f"成功率: {self.success_rate:.2f}")
        if self.parameter_bindings:
            lines.append("参数绑定:")
            for pb in sorted(self.parameter_bindings, key=lambda x: -x.frequency):
                suffix = f" - {pb.semantics}" if pb.semantics else ""
                lines.append(f"  --{pb.param_name} {pb.param_value} ({pb.frequency}次){suffix}")
        lines.append(f"来源: {self.source_type}")
        if self.last_executed_at:
            lines.append(f"最近执行: {self.last_executed_at}")
        return "\n".join(line for line in lines if line.strip())

    def build_summary_text(self) -> str:
        label = self.command_category or "general"
        name = self.command_name
        bindings = sorted(self.parameter_bindings, key=lambda x: -x.frequency)
        full_command = self.command_template or name
        for pb in bindings:
            full_command = full_command.replace(f"{{{pb.param_name}}}", pb.param_value)
        params = " ".join(f"--{pb.param_name}" for pb in bindings[:5])
        semantic = f" - {self.semantic_description}" if self.semantic_description else ""
        summary = f"{full_command} | {name} [{label}] {params} ({self.execution_count}次){semantic}"
        return truncate_text(clean_text(summary), 200)

    def _execution_importance(self) -> float:
        """将执行次数归一化为 importance 值 (0-1)，使用对数压缩避免线性膨胀。"""
        if self.execution_count <= 0:
            return 0.0
        import math
        return _clamp(math.log(self.execution_count + 1) / math.log(101))

    def _freshness(self) -> float | None:
        if not self.last_executed_at:
            return None
        from src.utils.time import utc_now_iso
        try:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            last = datetime.fromisoformat(self.last_executed_at.replace("Z", "+00:00"))
            hours = max(0.0, (now - last).total_seconds() / 3600.0)
            return _clamp(1.0 - hours / (24 * 30))
        except Exception:
            return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "user_id": self.user_id,
            "command_template": self.command_template,
            "command_name": self.command_name,
            "command_category": self.command_category,
            "project_id": self.project_id,
            "repo_id": self.repo_id,
            "semantic_description": self.semantic_description,
            "scenario_keywords": list(self.scenario_keywords),
            "parameter_bindings": [
                {
                    "param_name": pb.param_name,
                    "param_value": pb.param_value,
                    "frequency": pb.frequency,
                    "semantics": pb.semantics,
                }
                for pb in self.parameter_bindings
            ],
            "execution_count": self.execution_count,
            "last_executed_at": self.last_executed_at,
            "success_count": self.success_count,
            "success_rate": self.success_rate,
            "source_type": self.source_type,
            "source_event_id": self.source_event_id,
            "status": self.status,
            "overwrite_of": self.overwrite_of,
            "superseded_by": self.superseded_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_memory_core(cls, memory: MemoryCore | dict[str, Any]) -> CLIWorkflowMemory:
        data = memory if isinstance(memory, dict) else {
            name: getattr(memory, name)
            for name in MemoryCore.__dataclass_fields__
            if hasattr(memory, name)
        }
        entities = list(data.get("entities") or data.get("entities_json") or [])
        tags = list(data.get("tags") or data.get("tags_json") or [])
        content = str(data.get("content_text") or "")

        user_id = _field_from_entities(entities, "user_id") or ""
        project_id = _field_from_entities(entities, "project_id")
        repo_id = _field_from_entities(entities, "repo_id")
        command_name = _field_from_entities(entities, "command_name") or ""
        command_template = _line_value(content, "命令模板") or command_name
        command_category = _line_value(content, "分类") or "general"
        semantic_description = _line_value(content, "语义")
        scenario_line = _line_value(content, "场景关键词") or ""
        scenario_keywords = [
            clean_text(part)
            for part in scenario_line.split(",")
            if clean_text(part)
        ]
        for tag in tags:
            if tag.startswith("category:") and not command_category:
                command_category = tag.split(":", 1)[1]
                break
        execution_count = int(_line_value(content, "执行次数") or "1")
        success_rate_str = _line_value(content, "成功率") or "0.0"
        try:
            success_rate = float(success_rate_str)
        except (ValueError, TypeError):
            success_rate = 0.0
        success_count = round(success_rate * execution_count)
        source_type = _line_value(content, "来源") or str(data.get("source_type") or "shell")
        parameter_bindings = _param_tags_to_bindings(tags)
        status: WorkflowStatus = "superseded" if data.get("status") == "superseded" else "active"

        return cls(
            workflow_id=str(data.get("memory_id")),
            user_id=user_id,
            command_template=command_template,
            command_name=command_name,
            command_category=command_category,
            project_id=project_id,
            repo_id=repo_id,
            semantic_description=semantic_description,
            scenario_keywords=scenario_keywords,
            parameter_bindings=parameter_bindings,
            execution_count=execution_count,
            last_executed_at=data.get("updated_at") or data.get("created_at"),
            success_count=success_count,
            source_type=source_type,
            source_event_id=data.get("source_event_id"),
            status=status,
            overwrite_of=data.get("overwrite_of"),
            superseded_by=data.get("superseded_by"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass(slots=True)
class CLIWorkflowCandidate:
    memory: CLIWorkflowMemory
    evidence_text: str
    signals: list[str] = field(default_factory=list)
    needs_review: bool = False

    def is_admissible(self, min_confidence: float = 0.3) -> bool:
        if not clean_text(self.memory.command_template):
            return False
        if (
            len(self.memory.parameter_bindings) == 0
            and self.memory.execution_count < 2
            and "known_toolchain" not in self.signals
        ):
            return False
        return True
