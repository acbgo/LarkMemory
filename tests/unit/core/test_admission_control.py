from __future__ import annotations

import unittest

from src.core.admission_control import AdmissionController
from src.core.memory_core import create_memory_core
from src.schemas import EventContext, NormalizedEvent


class TestAdmissionControl(unittest.TestCase):
    def setUp(self) -> None:
        self.controller = AdmissionController()

    def _event(self, event_type: str, text: str | None = None, payload: dict | None = None) -> NormalizedEvent:
        return NormalizedEvent(
            event_id="event-1",
            event_type=event_type,  # type: ignore[arg-type]
            source_type="feishu_chat",
            occurred_at="2026-04-27T00:00:00Z",
            context=EventContext(),
            content_text=text,
            payload=payload or {},
        )

    def test_empty_event_rejected(self) -> None:
        decision = self.controller.evaluate_event(self._event("chat_message"))

        self.assertFalse(decision.admitted)

    def test_strong_decision_text_admitted_active(self) -> None:
        decision = self.controller.evaluate_event(self._event("chat_message", "决定采用方案 B"))

        self.assertTrue(decision.admitted)
        self.assertEqual(decision.status, "active")

    def test_memory_feedback_admitted(self) -> None:
        decision = self.controller.evaluate_event(self._event("memory_feedback"))

        self.assertTrue(decision.admitted)

    def test_llm_event_gate_rejects_non_memory_event(self) -> None:
        class FakeLLM:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            async def ajson(self, system_prompt: str | None, user_prompt: str, **kwargs: object) -> dict[str, object]:
                self.calls.append({"system_prompt": system_prompt or "", "user_prompt": user_prompt, "kwargs": kwargs})
                return {"should_extract": False}

        llm = FakeLLM()
        controller = AdmissionController(llm_client=llm)

        decision = controller.evaluate_event(self._event("chat_message", "收到，下午见"), domain="project_decision")

        self.assertFalse(decision.admitted)
        self.assertIn("LLM judged no long-term memory", decision.reason)
        self.assertEqual(decision.metadata["domain"], "project_decision")
        self.assertEqual(len(llm.calls), 1)

    def test_llm_event_gate_failure_falls_back_to_rules(self) -> None:
        class FailingLLM:
            async def ajson(self, *_args: object, **_kwargs: object) -> dict[str, object]:
                raise RuntimeError("llm unavailable")

        controller = AdmissionController(llm_client=FailingLLM())

        decision = controller.evaluate_event(self._event("chat_message", "决定采用方案 B"))

        self.assertTrue(decision.admitted)
        self.assertEqual(decision.reason, "strong memory signal")

    def test_memory_confidence_rules(self) -> None:
        low = create_memory_core(
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-1",
            content_text="Use SQLite",
            importance=0.5,
            confidence=0.2,
        )
        high = create_memory_core(
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-2",
            content_text="Use PostgreSQL",
            importance=0.9,
            confidence=0.9,
        )

        self.assertEqual(self.controller.evaluate_memory(low).status, "candidate")
        self.assertEqual(self.controller.evaluate_memory(high).status, "active")
