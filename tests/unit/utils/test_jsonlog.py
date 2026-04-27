from __future__ import annotations

import dataclasses
import json
import logging
import unittest
from datetime import datetime, timezone
from enum import Enum
from unittest.mock import Mock

from src.utils.jsonlog import (
    compact_dict,
    json_dumps,
    json_log_record,
    json_safe,
    log_json,
)


class Kind(Enum):
    MEMORY = "memory"


@dataclasses.dataclass
class Payload:
    created_at: datetime
    kind: Kind


class TestJsonLog(unittest.TestCase):
    def test_json_safe_handles_common_types(self) -> None:
        value = {
            "payload": Payload(
                created_at=datetime(2026, 4, 27, 3, 0, tzinfo=timezone.utc),
                kind=Kind.MEMORY,
            ),
            "items": {1, 2},
        }

        safe = json_safe(value)

        self.assertEqual(safe["payload"]["created_at"], "2026-04-27T03:00:00Z")
        self.assertEqual(safe["payload"]["kind"], "memory")
        self.assertEqual(sorted(safe["items"]), [1, 2])

    def test_json_dumps_outputs_parseable_json(self) -> None:
        dumped = json_dumps({"message": "你好", "kind": Kind.MEMORY})

        self.assertEqual(json.loads(dumped)["kind"], "memory")

    def test_json_log_record_contains_reserved_fields(self) -> None:
        record = json_log_record(
            "api.request",
            level="debug",
            message="done",
            timestamp="override",
            level_override="ignored",
            request_id="req-1",
        )

        self.assertEqual(record["level"], "DEBUG")
        self.assertEqual(record["event"], "api.request")
        self.assertEqual(record["message"], "done")
        self.assertIn("timestamp", record)
        self.assertNotEqual(record["timestamp"], "override")
        self.assertEqual(record["request_id"], "req-1")

    def test_compact_dict_does_not_mutate_original_and_truncates(self) -> None:
        original = {"text": "abcdef", "nested": {"text": "abcdef"}}
        compacted = compact_dict(original, max_text_chars=5)

        self.assertEqual(original["text"], "abcdef")
        self.assertEqual(compacted["text"], "ab...")
        self.assertEqual(compacted["nested"]["text"], "ab...")

    def test_log_json_calls_matching_logger_method(self) -> None:
        logger = Mock(spec=logging.Logger)

        log_json(logger, "api.ok", level="INFO", message="ok")
        log_json(logger, "api.fail", level="ERROR", message="failed")
        log_json(logger, "api.unknown", level="UNKNOWN", message="fallback")

        self.assertTrue(logger.info.called)
        self.assertTrue(logger.error.called)
        self.assertEqual(logger.info.call_count, 2)
