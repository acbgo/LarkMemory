from __future__ import annotations

import logging
from typing import Any

from src.domains.project_decision.models import ProjectDecision
from src.proactive.decider import ProjectDecisionProactiveDecider
from src.proactive.summarizer import ProjectDecisionProactiveSummarizer
from src.retrieval import RetrievalQuery
from src.schemas import NormalizedEvent
from src.storage import MemoryCoreStore, ProactiveStore


logger = logging.getLogger(__name__)


def _extract_topic(content: str) -> str:
    """Derive a short topic label from message content."""
    import re

    cleaned = content.strip()
    for sep in ("？", "?", "。", ".", "！", "!", "\n"):
        idx = cleaned.find(sep)
        if idx > 0:
            cleaned = cleaned[:idx]
            break
    cleaned = re.sub(r"现在有人提议|我想确认一下|我想了解一下|帮忙确认", "", cleaned)
    cleaned = cleaned.strip()
    return cleaned[:80] if len(cleaned) > 80 else cleaned


class ProactiveEngine:
    """在 ingest 成功后判断、检索、总结并触发主动推送。"""

    def __init__(
        self,
        *,
        memory_store: MemoryCoreStore,
        proactive_store: ProactiveStore,
        domain_handlers: dict[str, Any],
        notifier: Any | None = None,
        decider: Any | None = None,
        summarizer: Any | None = None,
        default_chat_id: str | None = None,
        related_top_k: int = 3,
        min_related_score: float = 0.55,
    ) -> None:
        self.memory_store = memory_store
        self.proactive_store = proactive_store
        self.domain_handlers = domain_handlers
        self.notifier = notifier
        self.decider = decider
        self.summarizer = summarizer
        self.default_chat_id = default_chat_id
        self.related_top_k = max(1, related_top_k)
        self.min_related_score = max(0.0, min(1.0, float(min_related_score)))

    def maybe_push(self, event: NormalizedEvent, *, domain: str | None, memory_ids: list[str]) -> None:
        if domain != "project_decision":
            return
        push_type = "decision_context_push"
        if self.proactive_store.is_sent(event.event_id, push_type):
            logger.info(
                "action=proactive_skip_duplicate_send event_id=%s push_type=%s",
                event.event_id,
                push_type,
            )
            return
        if memory_ids:
            memory_row = self.memory_store.get_memory(memory_ids[0])
            if memory_row is None:
                return
            memory = ProjectDecision.from_memory_core(memory_row)
        else:
            memory = self._build_synthetic_from_event(event)
            if memory is None:
                return
        self._run_push_pipeline(event, memory)

    def _run_push_pipeline(
        self,
        event: NormalizedEvent,
        memory: ProjectDecision,
    ) -> None:
        push_type = "decision_context_push"
        handler = self.domain_handlers.get("project_decision")
        if handler is None:
            return
        related_rows = self._load_related_rows(handler, memory)
        if not related_rows:
            self.proactive_store.upsert_record(
                event_id=event.event_id,
                domain="project_decision",
                push_type=push_type,
                status="skipped",
                reason="no_related_memories",
                memory_id=memory.decision_id,
            )
            return
        decider = self.decider or ProjectDecisionProactiveDecider(None)
        decision = decider.decide(event, memory, related_rows)
        push_type = decision.push_type or "decision_context_push"
        if not decision.should_push:
            self.proactive_store.upsert_record(
                event_id=event.event_id,
                domain="project_decision",
                push_type=push_type,
                status="skipped",
                reason=decision.reason or "decider_rejected",
                memory_id=memory.decision_id,
                related_memory_ids=[str(row.get("memory_id")) for row in related_rows if row.get("memory_id")],
            )
            return
        summarizer = self.summarizer or ProjectDecisionProactiveSummarizer(None)
        summary = summarizer.summarize(event, memory, related_rows)
        if summary.get("is_related") is False:
            self.proactive_store.upsert_record(
                event_id=event.event_id,
                domain="project_decision",
                push_type=push_type,
                status="skipped",
                reason="summary_unrelated",
                memory_id=memory.decision_id,
                related_memory_ids=list(summary.get("memory_ids") or []),
            )
            return
        target_chat_id = self._target_chat_id(event)
        if not target_chat_id or self.notifier is None:
            self.proactive_store.upsert_record(
                event_id=event.event_id,
                domain="project_decision",
                push_type=push_type,
                status="skipped",
                reason="missing_target_or_notifier",
                memory_id=memory.decision_id,
                related_memory_ids=[str(row.get("memory_id")) for row in related_rows if row.get("memory_id")],
                target_chat_id=target_chat_id,
            )
            return
        suggestion = {
            "type": push_type,
            "memory_id": memory.decision_id,
            "topic": memory.topic,
            "decision": memory.conclusion or memory.decision,
            "title": summary.get("title"),
            "summary": summary.get("summary"),
            "bullets": list(summary.get("bullets") or []),
            "related_memory_ids": list(summary.get("memory_ids") or []),
            "suggested_action": summary.get("suggested_action"),
        }
        try:
            self.notifier.send_decision_context(target_chat_id, suggestion)
        except Exception:
            logger.warning(
                "action=proactive_send_failed event_id=%s memory_id=%s",
                event.event_id,
                memory.decision_id,
                exc_info=True,
            )
            self.proactive_store.upsert_record(
                event_id=event.event_id,
                domain="project_decision",
                push_type=push_type,
                status="failed",
                reason="send_failed",
                memory_id=memory.decision_id,
                related_memory_ids=[str(row.get("memory_id")) for row in related_rows if row.get("memory_id")],
                target_chat_id=target_chat_id,
            )
            return
        self.proactive_store.upsert_record(
            event_id=event.event_id,
            domain="project_decision",
            push_type=push_type,
            status="sent",
            reason=decision.reason or "sent",
            memory_id=memory.decision_id,
            related_memory_ids=list(summary.get("memory_ids") or []),
            target_chat_id=target_chat_id,
        )

    def _load_related_rows(self, handler: Any, memory: ProjectDecision) -> list[dict[str, Any]]:
        query = RetrievalQuery(
            query_text=memory.conclusion or memory.decision,
            project_id=memory.project_id,
            team_id=memory.team_id,
            workspace_id=memory.workspace_id,
        )
        ranked = handler.retrieve(query, top_k=self.related_top_k)
        rows: list[dict[str, Any]] = []
        for result in ranked:
            if float(getattr(result, "final_score", 0.0) or 0.0) < self.min_related_score:
                continue
            memory_id = result.item.memory_id
            if memory_id == memory.decision_id:
                continue
            row = self.memory_store.get_memory(memory_id)
            if row is not None:
                rows.append(row)
        return rows

    def _target_chat_id(self, event: NormalizedEvent) -> str | None:
        chat_id = event.payload.get("chat_id")
        if isinstance(chat_id, str) and chat_id:
            return chat_id
        return self.default_chat_id

    @staticmethod
    def _build_synthetic_from_event(event: NormalizedEvent) -> ProjectDecision | None:
        """Build a ProjectDecision from raw event data when no memory was extracted."""
        content = event.content_text
        if not content:
            return None
        topic = _extract_topic(content)
        ctx = event.context
        return ProjectDecision(
            decision_id=event.event_id,
            project_id=ctx.project_id,
            workspace_id=ctx.workspace_id,
            team_id=ctx.team_id,
            thread_id=ctx.thread_id,
            topic=topic,
            conclusion=content,
            confidence=0.0,
            importance=0.0,
        )
