from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .embedding import TeamRetentionEmbeddingIndexer

from .models import TeamRetentionMemory


@dataclass(slots=True)
class TeamRetentionArbitrationResult:
    action: str  # "strengthen", "update", "candidate", "add"
    target_memory_id: str | None = None
    reason: str = ""


class TeamRetentionArbitrator:
    def __init__(
        self,
        llm_client: Any,
        embedding_indexer: TeamRetentionEmbeddingIndexer,
    ) -> None:
        self.llm_client = llm_client
        self.embedding_indexer = embedding_indexer

    def arbitrate(
        self,
        new_memory: TeamRetentionMemory,
        *,
        old_memories: list[TeamRetentionMemory],
    ) -> TeamRetentionArbitrationResult:
        if not old_memories:
            return TeamRetentionArbitrationResult(action="add", reason="no_similar_existing")

        try:
            verdict = _run_async(self._llm_arbitrate(new_memory, old_memories))
        except Exception:
            return TeamRetentionArbitrationResult(
                action="candidate",
                reason="arbitration_llm_failed",
            )

        action = verdict.get("action", "add")
        if action not in {"strengthen", "update", "candidate", "add"}:
            action = "add"

        target = verdict.get("target_memory_id")
        if not isinstance(target, str) or not target:
            target = None

        if action in {"strengthen", "update"} and target is None and old_memories:
            target = old_memories[0].retention_id

        return TeamRetentionArbitrationResult(
            action=action,
            target_memory_id=target,
            reason=str(verdict.get("reason", "")),
        )

    def load_old_memories(
        self,
        new_memory: TeamRetentionMemory,
        get_memory_fn: Any,
        *,
        top_k: int = 3,
    ) -> list[TeamRetentionMemory]:
        hits = self.embedding_indexer.query_similar(new_memory, top_k=top_k)
        if not hits:
            return []
        seen: set[str] = set()
        result: list[TeamRetentionMemory] = []
        for hit in hits:
            memory_id = hit.get("memory_id") or hit.get("id")
            if not isinstance(memory_id, str) or memory_id == new_memory.retention_id:
                continue
            if memory_id in seen:
                continue
            seen.add(memory_id)
            old = get_memory_fn(memory_id)
            if old is not None:
                result.append(old)
        return result

    async def _llm_arbitrate(
        self,
        new_memory: TeamRetentionMemory,
        old_memories: list[TeamRetentionMemory],
    ) -> dict[str, Any]:
        return await self.llm_client.ajson(
            _ARBITRATION_SYSTEM_PROMPT,
            _arbitration_user_prompt(new_memory, old_memories),
            schema=_ARBITRATION_SCHEMA,
            temperature=0,
            max_tokens=400,
        )


_ARBITRATION_SYSTEM_PROMPT = (
    "你是团队记忆仲裁器。给定一条新记忆和多条语义相似的旧记忆，判断它们的关系。\n\n"
    "Actions:\n"
    "- strengthen: 新旧指向同一个事实（措辞不同但语义相同），不需要创建新记忆，只需强化旧记忆\n"
    "- update: 新事实明确替代某条旧记忆（信息更新、置信度更高、或明确纠正）\n"
    "- candidate: 新旧可能存在冲突但证据不足以确定替代关系，新记忆存为candidate待人工确认\n"
    "- add: 新事实与所有旧记忆无关，是全新知识\n\n"
    "判断标准:\n"
    "1. 比较 fact_type 是否相关\n"
    "2. 比较 fact_value 的主体、属性、约束条件\n"
    "3. 比较 confidence —— 谁的确定性更高\n"
    "4. 区分「同一事实的不同表述」和「不同但相关的事实」\n"
    "5. 区分「信息更新（update）」和「相关但独立的新事实（add）」\n"
    "只返回 JSON，不要输出其他文字。"
)


def _arbitration_user_prompt(
    new_memory: TeamRetentionMemory,
    old_memories: list[TeamRetentionMemory],
) -> str:
    old_blocks: list[str] = []
    for i, old in enumerate(old_memories, start=1):
        block = (
            f"EXISTING #{i} [id: {old.retention_id}]\n"
            f"  fact_type: {old.fact_type}\n"
            f"  fact_value: {old.fact_value}\n"
            f"  confidence: {old.confidence:.2f}\n"
            f"  risk_level: {old.risk_level}\n"
        )
        old_blocks.append(block)

    new_block = (
        f"NEW MEMORY\n"
        f"  fact_type: {new_memory.fact_type}\n"
        f"  fact_value: {new_memory.fact_value}\n"
        f"  confidence: {new_memory.confidence:.2f}\n"
        f"  risk_level: {new_memory.risk_level}\n"
    )

    return json.dumps(
        {
            "new": new_block,
            "existing": "\n".join(old_blocks),
            "task": "判断新记忆与每条已有记忆的关系，返回 action 和 reason。",
        },
        ensure_ascii=False,
    )


_ARBITRATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["strengthen", "update", "candidate", "add"]},
        "target_memory_id": {"type": ["string", "null"]},
        "reason": {"type": "string"},
    },
    "required": ["action", "target_memory_id", "reason"],
}


def _run_async(awaitable: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    raise RuntimeError("TeamRetentionArbitrator cannot run inside an active event loop")
