from __future__ import annotations

import unittest

from src.core.access_tracker import AccessRecord, AccessTracker


class TestAccessTracker(unittest.TestCase):
    def test_record_access_and_recent_limit(self) -> None:
        tracker = AccessTracker(max_recent=1)
        first = tracker.record_access("mem-1")
        second = tracker.record_access("mem-2")

        self.assertTrue(first.access_id.startswith("acc-"))
        self.assertEqual(tracker.recent_records(), [second])

    def test_persist_fn_called_and_exception_swallowed(self) -> None:
        calls: list[AccessRecord] = []
        tracker = AccessTracker(persist_fn=calls.append)
        record = tracker.record_access("mem-1")

        self.assertEqual(calls, [record])

        failing = AccessTracker(persist_fn=lambda record: (_ for _ in ()).throw(RuntimeError("boom")))
        failing.record_access("mem-2")
        self.assertEqual(len(failing.recent_records()), 1)

    def test_record_feedback_and_stats(self) -> None:
        tracker = AccessTracker()
        tracker.record_access("mem-1")
        feedback = tracker.record_feedback("mem-1", "useful")

        self.assertEqual(feedback.access_type, "feedback")
        self.assertEqual(feedback.feedback_signal, "useful")
        self.assertEqual(tracker.stats_by_memory()["mem-1"], {"retrieved": 1, "feedback": 1})

