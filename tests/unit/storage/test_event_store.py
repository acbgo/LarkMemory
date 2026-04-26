from __future__ import annotations

import unittest
import uuid
import shutil
from pathlib import Path

from src.schemas import EventContext, NormalizedEvent
from src.storage import EventStore


class TestEventStore(unittest.TestCase):
    def setUp(self) -> None:
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        self.temp_dir = root / f"event-store-{uuid.uuid4().hex}"
        self.temp_dir.mkdir()
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.db_path = str(self.temp_dir / "test.db")
        self.store = EventStore(self.db_path)
        self.store.create_table()

    def test_insert_and_get_event(self) -> None:
        event = NormalizedEvent(
            event_id="event-1",
            event_type="command_finished",
            source_type="shell",
            occurred_at="2026-04-26T12:00:00Z",
            context=EventContext(
                user_id="user-1",
                project_id="project-1",
                repo_id="repo-1",
            ),
            title="Build completed",
            content_text="npm run build",
            payload={"exit_code": 0},
            raw_payload={"stdout": "ok"},
            tags=["build"],
        )

        inserted_id = self.store.insert_event(event)
        fetched = self.store.get_event(inserted_id)

        self.assertEqual(inserted_id, "event-1")
        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched["event_type"], "command_finished")
        self.assertEqual(fetched["project_id"], "project-1")
        self.assertEqual(fetched["payload_json"]["exit_code"], 0)
        self.assertEqual(fetched["raw_payload_json"]["stdout"], "ok")
        self.assertEqual(fetched["tags_json"], ["build"])

    def test_list_events_orders_by_occurred_at_desc(self) -> None:
        older = NormalizedEvent(
            event_id="event-older",
            event_type="chat_message",
            source_type="feishu_chat",
            occurred_at="2026-04-26T10:00:00Z",
            context=EventContext(project_id="project-1"),
            content_text="older",
        )
        newer = NormalizedEvent(
            event_id="event-newer",
            event_type="chat_message",
            source_type="feishu_chat",
            occurred_at="2026-04-26T11:00:00Z",
            context=EventContext(project_id="project-1"),
            content_text="newer",
        )

        self.store.insert_event(older)
        self.store.insert_event(newer)

        rows = self.store.list_events()

        self.assertEqual(rows[0]["event_id"], "event-newer")
        self.assertEqual(rows[1]["event_id"], "event-older")

    def test_list_events_by_source_filters_and_preserves_compat_fields(self) -> None:
        shell_event = NormalizedEvent(
            event_id="event-shell",
            event_type="command_finished",
            source_type="shell",
            occurred_at="2026-04-26T12:00:00Z",
            context=EventContext(user_id="user-1"),
            payload={"exit_code": 0},
            raw_payload={"stdout": "ok"},
            tags=["shell"],
        )
        chat_event = NormalizedEvent(
            event_id="event-chat",
            event_type="chat_message",
            source_type="feishu_chat",
            occurred_at="2026-04-26T13:00:00Z",
            context=EventContext(user_id="user-1"),
        )
        self.store.insert_event(shell_event)
        self.store.insert_event(chat_event)

        rows = self.store.list_events_by_source("shell")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event_id"], "event-shell")
        self.assertEqual(rows[0]["payload_json"]["exit_code"], 0)
        self.assertEqual(rows[0]["payload"]["exit_code"], 0)
        self.assertEqual(rows[0]["tags_json"], ["shell"])
        self.assertEqual(rows[0]["tags"], ["shell"])

    def test_list_events_for_scope_filters_by_project_team_and_user(self) -> None:
        self.store.insert_event(
            NormalizedEvent(
                event_id="event-1",
                event_type="chat_message",
                source_type="feishu_chat",
                occurred_at="2026-04-26T10:00:00Z",
                context=EventContext(project_id="project-1", team_id="team-1", user_id="user-1"),
            )
        )
        self.store.insert_event(
            NormalizedEvent(
                event_id="event-2",
                event_type="chat_message",
                source_type="feishu_chat",
                occurred_at="2026-04-26T11:00:00Z",
                context=EventContext(project_id="project-1", team_id="team-2", user_id="user-2"),
            )
        )

        rows = self.store.list_events_for_scope(project_id="project-1", team_id="team-1")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event_id"], "event-1")

    def test_list_events_by_time_range_and_delete_old_events(self) -> None:
        self.store.insert_event(
            NormalizedEvent(
                event_id="event-older",
                event_type="chat_message",
                source_type="feishu_chat",
                occurred_at="2026-04-26T09:00:00Z",
                context=EventContext(project_id="project-1"),
            )
        )
        self.store.insert_event(
            NormalizedEvent(
                event_id="event-middle",
                event_type="chat_message",
                source_type="feishu_chat",
                occurred_at="2026-04-26T10:00:00Z",
                context=EventContext(project_id="project-1"),
            )
        )
        self.store.insert_event(
            NormalizedEvent(
                event_id="event-newer",
                event_type="chat_message",
                source_type="feishu_chat",
                occurred_at="2026-04-26T11:00:00Z",
                context=EventContext(project_id="project-1"),
            )
        )

        rows = self.store.list_events_by_time_range(
            "2026-04-26T09:30:00Z",
            "2026-04-26T11:00:00Z",
        )
        deleted = self.store.delete_old_events("2026-04-26T10:00:00Z")
        remaining = self.store.list_events()

        self.assertEqual([row["event_id"] for row in rows], ["event-newer", "event-middle"])
        self.assertEqual(deleted, 1)
        self.assertEqual([row["event_id"] for row in remaining], ["event-newer", "event-middle"])
