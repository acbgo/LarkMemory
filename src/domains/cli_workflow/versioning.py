from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from src.storage import MemoryCoreStore
from src.utils.time import utc_now_iso

from .models import CLIWorkflowMemory


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class VersionDecision:
    should_reinforce: bool = False
    should_supersede: bool = False
    old_memory_id: str | None = None
    old_memory: dict[str, Any] | None = None
    message: str | None = None


class CLIWorkflowVersionManager:

    def __init__(self, memory_store: MemoryCoreStore) -> None:
        self.memory_store = memory_store

    def detect_update(self, incoming: CLIWorkflowMemory) -> VersionDecision:
        existing = self._find_existing(incoming)
        if existing is None:
            return VersionDecision(message="new")

        old_memory = CLIWorkflowMemory.from_memory_core(existing)
        old_memory_id = old_memory.workflow_id

        # 同源强化：同一个 source_type 的重复执行
        if incoming.source_type == old_memory.source_type:
            if incoming.source_type == "shell":
                # Shell: 同命令模板 → 强化更新
                return VersionDecision(
                    should_reinforce=True,
                    old_memory_id=old_memory_id,
                    old_memory=existing,
                    message="shell_reinforce",
                )
            else:
                # OpenClaw: 同源显式教学 → 参数可能不同，覆盖
                if self._params_differ(incoming, old_memory):
                    return VersionDecision(
                        should_supersede=True,
                        old_memory_id=old_memory_id,
                        old_memory=existing,
                        message="openclaw_params_changed",
                    )
                return VersionDecision(
                    should_reinforce=True,
                    old_memory_id=old_memory_id,
                    old_memory=existing,
                    message="openclaw_reinforce",
                )

        # 跨源：OpenClaw 覆盖 Shell
        if incoming.source_type == "openclaw" and old_memory.source_type == "shell":
            return VersionDecision(
                should_supersede=True,
                old_memory_id=old_memory_id,
                old_memory=existing,
                message="openclaw_overrides_shell",
            )

        # Shell 不应覆盖已有的 OpenClaw 记忆
        if incoming.source_type == "shell" and old_memory.source_type == "openclaw":
            return VersionDecision(
                should_reinforce=True,
                old_memory_id=old_memory_id,
                old_memory=existing,
                message="shell_reinforces_openclaw",
            )

        return VersionDecision(message="new")

    def apply_reinforce(self, memory_id: str, incoming: CLIWorkflowMemory) -> None:
        existing_row = self.memory_store.get_memory(memory_id)
        if existing_row is None:
            return

        existing = CLIWorkflowMemory.from_memory_core(existing_row)
        existing.execution_count += 1
        existing.last_executed_at = incoming.last_executed_at or utc_now_iso()
        if incoming.source_type == "shell":
            existing.success_count += incoming.success_count

        # 合并参数绑定：更新频率
        self._merge_bindings(existing, incoming.parameter_bindings)

        # 重新写回 MemoryCore
        core = existing.to_memory_core()
        core.updated_at = utc_now_iso()
        self._update_memory_core(memory_id, existing)
        logger.info(
            "action=reinforce memory_id=%s execution_count=%s",
            memory_id,
            existing.execution_count,
        )

    def apply_supersede(self, old_memory_id: str, new_memory_id: str) -> None:
        self.memory_store.mark_superseded(old_memory_id, new_memory_id)
        logger.info(
            "action=supersede old_memory_id=%s new_memory_id=%s",
            old_memory_id,
            new_memory_id,
        )

    def _find_existing(self, incoming: CLIWorkflowMemory) -> dict[str, Any] | None:
        filters: dict[str, str] = {"command_name": incoming.command_name}
        if incoming.user_id:
            filters["user_id"] = incoming.user_id
        if incoming.project_id:
            filters["project_id"] = incoming.project_id
        rows = self.memory_store.search_memory_candidates(
            domain="cli_workflow",
            status="active",
            entity_filters=filters,
            limit=5,
        )
        return rows[0] if rows else None

    @staticmethod
    def _params_differ(a: CLIWorkflowMemory, b: CLIWorkflowMemory) -> bool:
        a_params = {(pb.param_name, pb.param_value) for pb in a.parameter_bindings}
        b_params = {(pb.param_name, pb.param_value) for pb in b.parameter_bindings}
        return a_params != b_params

    @staticmethod
    def _merge_bindings(existing: CLIWorkflowMemory, incoming_bindings: list[Any]) -> None:
        binding_map: dict[tuple[str, str], Any] = {
            (pb.param_name, pb.param_value): pb for pb in existing.parameter_bindings
        }
        for pb in incoming_bindings:
            key = (pb.param_name, pb.param_value)
            if key in binding_map:
                binding_map[key].frequency += pb.frequency
            else:
                binding_map[key] = pb
        existing.parameter_bindings = list(binding_map.values())

    def _update_memory_core(self, memory_id: str, memory: CLIWorkflowMemory) -> None:
        core = memory.to_memory_core()
        core.updated_at = utc_now_iso()
        import json
        self.memory_store.execute(
            """
            UPDATE memory_core
            SET content_text = ?,
                summary_text = ?,
                entities_json = ?,
                tags_json = ?,
                importance = ?,
                confidence = ?,
                freshness_score = ?,
                updated_at = ?
            WHERE memory_id = ?
            """,
            (
                core.content_text,
                core.summary_text,
                json.dumps(core.entities, ensure_ascii=True),
                json.dumps(core.tags, ensure_ascii=True),
                core.importance,
                core.confidence,
                core.freshness_score,
                core.updated_at,
                memory_id,
            ),
        )
