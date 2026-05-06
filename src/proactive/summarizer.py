from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.domains.project_decision.models import ProjectDecision
from src.schemas import NormalizedEvent


logger = logging.getLogger(__name__)


class ProjectDecisionProactiveSummarizer:
    """将当前决策和相关历史决策总结成适合飞书卡片的结构化摘要。"""

    def __init__(self, llm_client: Any | None) -> None:
        self.llm_client = llm_client

    def summarize(
        self,
        event: NormalizedEvent,
        memory: ProjectDecision,
        related_rows: list[dict[str, object]],
    ) -> dict[str, object]:
        if self.llm_client is None:
            return self._fallback_summary(memory, related_rows)
        schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "summary": {"type": "string"},
                "bullets": {"type": "array", "items": {"type": "string"}},
                "memory_ids": {"type": "array", "items": {"type": "string"}},
                "is_related": {"type": "boolean"},
                "suggested_action": {"type": "string"},
            },
            "required": ["summary"],
        }
        try:
            raw = _run_async(
                self.llm_client.ajson(
                    (
                        "你是项目决策主动推送摘要器。"
                        "如果当前消息是对历史决策的询问，基于 related_memories 总结相关历史决策。"
                        "如果当前消息是新决策，总结历史决策与此新决策的关联。"
                        "只输出 JSON。保持summary尽可能简短"
                    ),
                    self._build_user_prompt(event, memory, related_rows),
                    schema=schema,
                    temperature=0,
                )
            )
            logger.info(
                "action=proactive_summarizer_result event_id=%s memory_id=%s raw=%s",
                event.event_id,
                memory.decision_id,
                raw,
            )
            return self._normalize_result(raw, memory, related_rows)
        except Exception:
            logger.warning(
                "action=proactive_summarizer_failed event_id=%s memory_id=%s",
                event.event_id,
                memory.decision_id,
                exc_info=True,
            )
            return self._fallback_summary(memory, related_rows)

    def _build_user_prompt(
        self,
        event: NormalizedEvent,
        memory: ProjectDecision,
        related_rows: list[dict[str, object]],
    ) -> str:
        related_lines = []
        for row in related_rows:
            created = str(row.get("created_at") or "")[:10]
            related_lines.append(
                f"- [{created}] memory_id={row.get('memory_id')} summary={row.get('summary_text') or row.get('content_text')}"
            )
        return (
            f"当前消息(topic)={memory.topic}\n"
            f"当前消息内容={memory.conclusion or memory.decision}\n"
            f"原始消息={event.content_text or ''}\n"
            "相关历史决策:\n"
            + "\n".join(related_lines)
            + "\n\n请基于「相关历史决策」生成摘要，说明这些历史决策是什么、与当前消息的关联。"
        )

    def _normalize_result(
        self,
        raw: dict[str, object],
        memory: ProjectDecision,
        related_rows: list[dict[str, object]],
    ) -> dict[str, object]:
        """Fill missing LLM response fields with sensible defaults from actual data."""
        fallback = self._fallback_summary(memory, related_rows)
        return {
            "title": raw.get("title") or fallback["title"],
            "summary": raw.get("summary") or fallback["summary"],
            "bullets": raw.get("bullets") or fallback["bullets"],
            "memory_ids": raw.get("memory_ids") or fallback["memory_ids"],
            "is_related": raw.get("is_related", fallback["is_related"]),
            "suggested_action": raw.get("suggested_action") or fallback["suggested_action"],
        }

    def _fallback_summary(
        self,
        memory: ProjectDecision,
        related_rows: list[dict[str, object]],
    ) -> dict[str, object]:
        seen: set[str] = set()
        bullets: list[str] = []
        memory_ids: list[str] = []
        for row in related_rows[:5]:
            text = str(row.get("summary_text") or row.get("content_text") or "")[:120]
            key = text.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            created = str(row.get("created_at") or "")[:10]
            prefix = f"[{created}] " if created else ""
            bullets.append(f"{prefix}{text}")
            mid = row.get("memory_id")
            if mid:
                memory_ids.append(str(mid))
        return {
            "title": "发现相关历史决策",
            "summary": f"当前决策“{memory.topic}”可能和之前的历史结论有关。",
            "bullets": bullets,
            "memory_ids": memory_ids,
            "is_related": bool(memory_ids),
            "suggested_action": "查看历史决策上下文",
        }


def _run_async(awaitable: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    raise RuntimeError("ProjectDecisionProactiveSummarizer cannot block inside an async context.")
