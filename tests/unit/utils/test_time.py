from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src.utils.time import (
    days_between,
    format_iso,
    is_expired,
    parse_iso,
    time_window,
    to_utc,
    utc_now,
)


class TestTime(unittest.TestCase):
    def test_utc_now_returns_aware_utc(self) -> None:
        value = utc_now()

        self.assertIsNotNone(value.tzinfo)
        self.assertEqual(value.tzinfo, timezone.utc)

    def test_format_iso_outputs_z(self) -> None:
        value = datetime(2026, 4, 27, 3, 0, 0, tzinfo=timezone.utc)

        self.assertEqual(format_iso(value), "2026-04-27T03:00:00Z")

    def test_parse_iso_supports_z_offset_and_naive(self) -> None:
        self.assertEqual(parse_iso("2026-04-27T03:00:00Z").tzinfo, timezone.utc)
        self.assertEqual(parse_iso("2026-04-27T11:00:00+08:00").hour, 3)
        self.assertEqual(parse_iso("2026-04-27T03:00:00").tzinfo, timezone.utc)

    def test_parse_iso_rejects_empty_and_invalid(self) -> None:
        for value in ("", "not-a-date"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_iso(value)

    def test_to_utc_treats_naive_as_utc(self) -> None:
        value = to_utc(datetime(2026, 4, 27, 3, 0, 0))

        self.assertEqual(value.tzinfo, timezone.utc)
        self.assertEqual(value.hour, 3)

    def test_time_window(self) -> None:
        start, end = time_window("2026-04-27T03:00:00Z", days=1, hours=2)

        self.assertEqual(start, "2026-04-26T01:00:00Z")
        self.assertEqual(end, "2026-04-27T03:00:00Z")

    def test_time_window_requires_duration(self) -> None:
        with self.assertRaises(ValueError):
            time_window("2026-04-27T03:00:00Z")

    def test_is_expired(self) -> None:
        now = datetime(2026, 4, 27, 3, 0, 0, tzinfo=timezone.utc)

        self.assertFalse(is_expired(None, now=now))
        self.assertTrue(is_expired(now - timedelta(seconds=1), now=now))
        self.assertFalse(is_expired(now + timedelta(seconds=1), now=now))

    def test_days_between(self) -> None:
        days = days_between("2026-04-26T00:00:00Z", "2026-04-27T12:00:00Z")

        self.assertEqual(days, 1.5)
