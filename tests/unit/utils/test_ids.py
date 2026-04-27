from __future__ import annotations

import unittest

from src.utils.ids import (
    benchmark_run_id,
    event_id,
    is_typed_id,
    memory_id,
    new_id,
    parse_typed_id,
    query_id,
    request_id,
)


class TestIds(unittest.TestCase):
    def test_new_id_returns_prefix(self) -> None:
        value = new_id("evt")

        self.assertTrue(value.startswith("evt-"))
        self.assertEqual(len(value.split("-", 1)[1]), 12)

    def test_new_id_normalizes_prefix(self) -> None:
        value = new_id(" EVT_1 ", size=4)

        self.assertTrue(value.startswith("evt_1-"))
        self.assertEqual(len(value.split("-", 1)[1]), 4)

    def test_new_id_rejects_invalid_prefix_and_size(self) -> None:
        with self.assertRaises(ValueError):
            new_id("bad-prefix")
        with self.assertRaises(ValueError):
            new_id("")
        with self.assertRaises(ValueError):
            new_id("evt", size=0)
        with self.assertRaises(ValueError):
            new_id("evt", size=33)

    def test_parse_typed_id(self) -> None:
        self.assertEqual(parse_typed_id(" mem-abc-def "), ("mem", "abc-def"))

    def test_parse_typed_id_rejects_invalid_values(self) -> None:
        for value in ("", "missingdash", "-abc", "mem-"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_typed_id(value)

    def test_is_typed_id_supports_optional_prefix(self) -> None:
        self.assertTrue(is_typed_id("mem-abc"))
        self.assertTrue(is_typed_id("mem-abc", "mem"))
        self.assertFalse(is_typed_id("mem-abc", "evt"))
        self.assertFalse(is_typed_id("notvalid"))

    def test_convenience_id_prefixes(self) -> None:
        self.assertTrue(event_id().startswith("evt-"))
        self.assertTrue(memory_id().startswith("mem-"))
        self.assertTrue(query_id().startswith("qry-"))
        self.assertTrue(benchmark_run_id().startswith("bench-"))
        self.assertTrue(request_id().startswith("req-"))
