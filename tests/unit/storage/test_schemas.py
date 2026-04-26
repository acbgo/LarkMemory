from __future__ import annotations

import unittest

from src.schemas import EventContext, MemoryCore, NormalizedEvent


class TestSchemas(unittest.TestCase):
    def test_normalized_event_defaults(self) -> None:
        context = EventContext(
            user_id="user-1",
            project_id="project-1",
            repo_id="repo-1",
        )
        event = NormalizedEvent(
            event_id="event-1",
            event_type="command_finished",
            source_type="shell",
            occurred_at="2026-04-26T12:00:00Z",
            context=context,
            content_text="npm run build",
        )

        self.assertEqual(event.context.project_id, "project-1")
        self.assertEqual(event.tags, [])
        self.assertEqual(event.payload, {})
        self.assertEqual(event.raw_payload, {})

    def test_memory_core_defaults(self) -> None:
        memory = MemoryCore(
            memory_id="memory-1",
            domain="cli_workflow",
            memory_type="command_template",
            scope="project",
            source_type="shell",
            source_ref="event-1",
            content_text="npm run build",
        )

        self.assertEqual(memory.status, "active")
        self.assertEqual(memory.entities, [])
        self.assertEqual(memory.tags, [])
        self.assertEqual(memory.importance, 0.0)
        self.assertEqual(memory.confidence, 0.0)
