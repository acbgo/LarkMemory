from __future__ import annotations

from dataclasses import asdict
import shutil
import unittest
import uuid
from pathlib import Path

from src.domains.project_decision.models import ProjectDecision
from src.proactive.decider import ProactiveDecision
from src.proactive.engine import ProactiveEngine
from src.retrieval import RankedMemory, RetrievalQuery, memory_item_from_core
from src.schemas import EventContext, NormalizedEvent
from src.storage import MemoryCoreStore, ProactiveStore


class FakeProjectDecisionHandler:
    domain = "project_decision"

    def __init__(self, ranked_rows: list[dict[str, object]] | None = None, *, score: float = 0.9) -> None:
        self.ranked_rows = list(ranked_rows or [])
        self.score = score
        self.queries: list[RetrievalQuery] = []

    def retrieve(self, query: RetrievalQuery, *, top_k: int) -> list[RankedMemory]:
        self.queries.append(query)
        rows = self.ranked_rows[:top_k]
        return [
            RankedMemory(item=memory_item_from_core(row), final_score=self.score, rank=index + 1)
            for index, row in enumerate(rows)
        ]


class FakeDecider:
    def __init__(self, decision: ProactiveDecision) -> None:
        self.decision = decision
        self.calls = 0

    def decide(
        self,
        event: NormalizedEvent,
        memory: ProjectDecision,
        related_rows: list[dict[str, object]] | None = None,
    ) -> ProactiveDecision:
        self.calls += 1
        self.related_rows = list(related_rows or [])
        return self.decision


class FakeSummarizer:
    def __init__(self, summary: dict[str, object]) -> None:
        self.summary = summary
        self.calls = 0

    def summarize(
        self,
        event: NormalizedEvent,
        memory: ProjectDecision,
        related_rows: list[dict[str, object]],
    ) -> dict[str, object]:
        self.calls += 1
        return self.summary


class FakeNotifier:
    def __init__(self, should_fail: bool = False) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.should_fail = should_fail

    def send_decision_context(self, chat_id: str, suggestion: dict[str, object]) -> object:
        self.calls.append((chat_id, suggestion))
        if self.should_fail:
            raise RuntimeError("send failed")
        return {"ok": True}


def _event() -> NormalizedEvent:
    return NormalizedEvent(
        event_id=f"event-{uuid.uuid4().hex}",
        event_type="chat_message",
        source_type="feishu_chat",
        occurred_at="2026-05-05T00:00:00Z",
        context=EventContext(project_id="project-1", team_id="team-1", workspace_id="workspace-1", thread_id="thread-1"),
        content_text="我们决定采用方案 B，而不是方案 A，因为接入成本更低。",
        payload={"chat_id": "oc_chat_1"},
    )


def _decision(memory_id: str, *, topic: str = "方案选型", decision_text: str = "采用方案 B") -> ProjectDecision:
    return ProjectDecision(
        decision_id=memory_id,
        project_id="project-1",
        workspace_id="workspace-1",
        team_id="team-1",
        thread_id="thread-1",
        topic=topic,
        decision=decision_text,
        conclusion=decision_text,
        stage="技术选型",
        source_ref="thread-1",
        confidence=0.9,
        importance=0.8,
        decided_at="2026-05-05T00:00:00Z",
    )


class TestProactiveEngine(unittest.TestCase):
    def setUp(self) -> None:
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        self.temp_dir = root / f"proactive-engine-{uuid.uuid4().hex}"
        self.temp_dir.mkdir()
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.memory_store = MemoryCoreStore(str(self.temp_dir / "memory.db"))
        self.memory_store.create_table()
        self.proactive_store = ProactiveStore(str(self.temp_dir / "proactive.db"))
        self.proactive_store.create_table()

    def test_maybe_push_marks_skipped_when_decider_rejects(self) -> None:
        event = _event()
        decision = _decision("mem-1", decision_text="采用方案 B，而不是方案 A")
        self.memory_store.insert_memory_core(decision.to_memory_core())
        handler = FakeProjectDecisionHandler()
        decider = FakeDecider(
            ProactiveDecision(False, confidence=0.2, reason="not_important", push_type="decision_context_push")
        )
        engine = ProactiveEngine(
            memory_store=self.memory_store,
            proactive_store=self.proactive_store,
            domain_handlers={"project_decision": handler},
            decider=decider,
            summarizer=FakeSummarizer({}),
            notifier=FakeNotifier(),
        )

        engine.maybe_push(event, domain="project_decision", memory_ids=["mem-1"])

        row = self.proactive_store.get_record(event.event_id, "decision_context_push")
        assert row is not None
        self.assertEqual(row["status"], "skipped")

    def test_maybe_push_sends_decision_context_and_records_sent(self) -> None:
        event = _event()
        decision = _decision("mem-1", decision_text="采用方案 B，而不是方案 A")
        related = _decision("mem-2", decision_text="之前也优先方案 B")
        self.memory_store.insert_memory_core(decision.to_memory_core())
        self.memory_store.insert_memory_core(related.to_memory_core())
        handler = FakeProjectDecisionHandler([asdict(related.to_memory_core())])
        notifier = FakeNotifier()
        engine = ProactiveEngine(
            memory_store=self.memory_store,
            proactive_store=self.proactive_store,
            domain_handlers={"project_decision": handler},
            decider=FakeDecider(
                ProactiveDecision(True, confidence=0.92, reason="has_history", push_type="decision_context_push")
            ),
            summarizer=FakeSummarizer(
                {
                    "title": "发现相关历史决策",
                    "summary": "可参考之前的方案 B 讨论",
                    "bullets": ["之前也优先方案 B"],
                    "memory_ids": ["mem-2"],
                    "suggested_action": "查看历史决策上下文",
                }
            ),
            notifier=notifier,
        )

        engine.maybe_push(event, domain="project_decision", memory_ids=["mem-1"])

        self.assertEqual(len(notifier.calls), 1)
        self.assertEqual(notifier.calls[0][0], "oc_chat_1")
        row = self.proactive_store.get_record(event.event_id, "decision_context_push")
        assert row is not None
        self.assertEqual(row["status"], "sent")
        self.assertEqual(row["memory_id"], "mem-1")
        self.assertEqual(row["related_memory_ids"], ["mem-2"])
        self.assertEqual(len(handler.queries), 1)
        self.assertEqual(len(engine.decider.related_rows), 1)  # type: ignore[attr-defined,union-attr]

    def test_maybe_push_skips_when_related_scores_are_too_low(self) -> None:
        event = _event()
        decision = _decision("mem-1", decision_text="采用方案 B，而不是方案 A")
        related = _decision("mem-2", decision_text="无关历史")
        self.memory_store.insert_memory_core(decision.to_memory_core())
        self.memory_store.insert_memory_core(related.to_memory_core())
        handler = FakeProjectDecisionHandler([asdict(related.to_memory_core())], score=0.2)
        notifier = FakeNotifier()
        engine = ProactiveEngine(
            memory_store=self.memory_store,
            proactive_store=self.proactive_store,
            domain_handlers={"project_decision": handler},
            decider=FakeDecider(
                ProactiveDecision(True, confidence=0.92, reason="has_history", push_type="decision_context_push")
            ),
            summarizer=FakeSummarizer({}),
            notifier=notifier,
            min_related_score=0.55,
        )

        engine.maybe_push(event, domain="project_decision", memory_ids=["mem-1"])

        self.assertEqual(notifier.calls, [])
        row = self.proactive_store.get_record(event.event_id, "decision_context_push")
        assert row is not None
        self.assertEqual(row["status"], "skipped")
        self.assertEqual(row["reason"], "no_related_memories")

    def test_maybe_push_skips_when_summarizer_marks_unrelated(self) -> None:
        event = _event()
        decision = _decision("mem-1", decision_text="采用方案 B，而不是方案 A")
        related = _decision("mem-2", decision_text="之前也优先方案 B")
        self.memory_store.insert_memory_core(decision.to_memory_core())
        self.memory_store.insert_memory_core(related.to_memory_core())
        handler = FakeProjectDecisionHandler([asdict(related.to_memory_core())])
        notifier = FakeNotifier()
        engine = ProactiveEngine(
            memory_store=self.memory_store,
            proactive_store=self.proactive_store,
            domain_handlers={"project_decision": handler},
            decider=FakeDecider(
                ProactiveDecision(True, confidence=0.92, reason="has_history", push_type="decision_context_push")
            ),
            summarizer=FakeSummarizer({"summary": "无直接关联", "is_related": False, "memory_ids": ["mem-2"]}),
            notifier=notifier,
        )

        engine.maybe_push(event, domain="project_decision", memory_ids=["mem-1"])

        self.assertEqual(notifier.calls, [])
        row = self.proactive_store.get_record(event.event_id, "decision_context_push")
        assert row is not None
        self.assertEqual(row["status"], "skipped")
        self.assertEqual(row["reason"], "summary_unrelated")

    def test_maybe_push_records_failed_when_notifier_raises(self) -> None:
        event = _event()
        decision = _decision("mem-1", decision_text="采用方案 B，而不是方案 A")
        related = _decision("mem-2", decision_text="之前也优先方案 B")
        self.memory_store.insert_memory_core(decision.to_memory_core())
        self.memory_store.insert_memory_core(related.to_memory_core())
        handler = FakeProjectDecisionHandler([asdict(related.to_memory_core())])
        engine = ProactiveEngine(
            memory_store=self.memory_store,
            proactive_store=self.proactive_store,
            domain_handlers={"project_decision": handler},
            decider=FakeDecider(
                ProactiveDecision(True, confidence=0.92, reason="has_history", push_type="decision_context_push")
            ),
            summarizer=FakeSummarizer(
                {
                    "title": "发现相关历史决策",
                    "summary": "可参考之前的方案 B 讨论",
                    "bullets": ["之前也优先方案 B"],
                    "memory_ids": ["mem-2"],
                    "suggested_action": "查看历史决策上下文",
                }
            ),
            notifier=FakeNotifier(should_fail=True),
        )

        engine.maybe_push(event, domain="project_decision", memory_ids=["mem-1"])

        row = self.proactive_store.get_record(event.event_id, "decision_context_push")
        assert row is not None
        self.assertEqual(row["status"], "failed")

    def test_maybe_push_sends_with_empty_memory_ids(self) -> None:
        """Synthetic path: empty memory_ids, valid content_text → full pipeline runs."""
        event = _event()
        related = _decision("mem-2", decision_text="之前也优先方案 B")
        self.memory_store.insert_memory_core(related.to_memory_core())
        handler = FakeProjectDecisionHandler([asdict(related.to_memory_core())])
        notifier = FakeNotifier()
        engine = ProactiveEngine(
            memory_store=self.memory_store,
            proactive_store=self.proactive_store,
            domain_handlers={"project_decision": handler},
            decider=FakeDecider(
                ProactiveDecision(True, confidence=0.92, reason="inquiry_context", push_type="decision_context_push")
            ),
            summarizer=FakeSummarizer(
                {
                    "title": "相关历史决策",
                    "summary": "之前关于方案 B 的讨论",
                    "bullets": ["之前也优先方案 B"],
                    "memory_ids": ["mem-2"],
                    "suggested_action": "查看历史决策上下文",
                }
            ),
            notifier=notifier,
        )

        engine.maybe_push(event, domain="project_decision", memory_ids=[])

        self.assertEqual(len(notifier.calls), 1)
        self.assertEqual(notifier.calls[0][0], "oc_chat_1")
        suggestion = notifier.calls[0][1]
        self.assertEqual(suggestion["memory_id"], event.event_id)
        self.assertEqual(suggestion["decision"], event.content_text)
        row = self.proactive_store.get_record(event.event_id, "decision_context_push")
        assert row is not None
        self.assertEqual(row["status"], "sent")
        self.assertEqual(len(handler.queries), 1)
        self.assertEqual(handler.queries[0].query_text, event.content_text)

    def test_maybe_push_skips_synthetic_when_no_content(self) -> None:
        """Synthetic path: empty content_text → returns without calling decider."""
        event = NormalizedEvent(
            event_id="evt-no-content",
            event_type="chat_message",
            source_type="feishu_chat",
            occurred_at="2026-05-05T00:00:00Z",
            context=EventContext(project_id="p1", team_id="t1", workspace_id="ws1"),
            content_text=None,
        )
        decider = FakeDecider(
            ProactiveDecision(True, confidence=0.9, reason="should_not_be_called")
        )
        engine = ProactiveEngine(
            memory_store=self.memory_store,
            proactive_store=self.proactive_store,
            domain_handlers={},
            decider=decider,
            notifier=FakeNotifier(),
        )

        engine.maybe_push(event, domain="project_decision", memory_ids=[])

        self.assertEqual(decider.calls, 0)

    def test_maybe_push_skips_synthetic_when_no_handler(self) -> None:
        """Synthetic path: without related recall there is no decider call."""
        event = _event()
        decider = FakeDecider(
            ProactiveDecision(False, confidence=0.3, reason="not_important", push_type="decision_context_push")
        )
        engine = ProactiveEngine(
            memory_store=self.memory_store,
            proactive_store=self.proactive_store,
            domain_handlers={},
            decider=decider,
            notifier=FakeNotifier(),
        )

        engine.maybe_push(event, domain="project_decision", memory_ids=[])

        row = self.proactive_store.get_record(event.event_id, "decision_context_push")
        self.assertIsNone(row)
        self.assertEqual(decider.calls, 0)
