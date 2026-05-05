from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from src.domains.project_decision.models import ProjectDecision
from src.schemas import NormalizedEvent


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ProactiveDecision:
    should_push: bool
    confidence: float = 0.0
    reason: str = ""
    push_type: str = "decision_context_push"


class ProjectDecisionProactiveDecider:
    """判断当前 project decision 是否值得主动推送历史上下文。"""

    def __init__(self, llm_client: Any | None, *, min_confidence: float = 0.8) -> None:
        self.llm_client = llm_client
        self.min_confidence = min_confidence

    def decide(self, event: NormalizedEvent, memory: ProjectDecision) -> ProactiveDecision:
        if self.llm_client is None:
            return ProactiveDecision(False, reason="llm_unavailable")
        schema = {
            "type": "object",
            "properties": {
                "push": {"type": "boolean"},
                "confidence": {"type": "number"},
                "reason": {"type": "string"},
                "push_type": {"type": "string"},
            },
            "required": ["push", "reason"],
        }
        try:
            raw = _run_async(
                self.llm_client.ajson(
                    "你是项目决策主动推送判断器。判断当前消息是否值得推送相关的历史决策上下文。只输出 JSON。",
                    (
                        "判断这条消息是否值得主动推送历史决策上下文。\n"
                        "标准：涉及对已有决策的询问、质疑、回顾或变更提议 → 推送；"
                        "与历史决策有明显关联的新决策声明 → 推送；"
                        "日常闲聊、纯信息通知、无明显关联 → 不推送。\n"
                        f"topic={memory.topic}\n"
                        f"decision={memory.conclusion or memory.decision}\n"
                        f"event_text={event.content_text or ''}"
                    ),
                    schema=schema,
                    temperature=0,
                )
            )
        except Exception:
            logger.warning(
                "action=proactive_decider_failed event_id=%s memory_id=%s",
                event.event_id,
                memory.decision_id,
                exc_info=True,
            )
            return ProactiveDecision(False, reason="llm_error")
        logger.info(
            "action=proactive_decider_result event_id=%s raw=%s",
            event.event_id,
            raw,
        )
        raw_should_push = raw.get("should_push") if "should_push" in raw else raw.get("push")
        confidence = _coerce_confidence(raw.get("confidence", 1.0))
        should_push = bool(raw_should_push) and confidence >= self.min_confidence
        return ProactiveDecision(
            should_push=should_push,
            confidence=confidence,
            reason=str(raw.get("reason") or ""),
            push_type=str(raw.get("push_type") or "decision_context_push"),
        )


def _coerce_confidence(value: object) -> float:
    if not isinstance(value, (int, float)):
        return 0.0
    return max(0.0, min(1.0, float(value)))


def _run_async(awaitable: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    raise RuntimeError("ProjectDecisionProactiveDecider cannot block inside an async context.")
