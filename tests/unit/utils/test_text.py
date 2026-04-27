from __future__ import annotations

import unittest

from src.utils.text import (
    clean_text,
    contains_any,
    normalize_keyword,
    normalize_whitespace,
    split_tags,
    truncate_text,
)


class TestText(unittest.TestCase):
    def test_normalize_whitespace(self) -> None:
        self.assertEqual(normalize_whitespace(" a \n\t b  "), "a b")
        self.assertEqual(normalize_whitespace(None), "")

    def test_clean_text_handles_none_control_chars_and_max_chars(self) -> None:
        self.assertEqual(clean_text(None), "")
        self.assertEqual(clean_text("a\x00\n b\tc"), "a b c")
        self.assertEqual(clean_text("abcdef", max_chars=5), "ab...")
        with self.assertRaises(ValueError):
            clean_text("abc", max_chars=0)

    def test_truncate_text(self) -> None:
        self.assertEqual(truncate_text("abc", 5), "abc")
        self.assertEqual(truncate_text("abcdef", 5), "ab...")
        self.assertEqual(truncate_text("abcdef", 2), "ab")
        self.assertLessEqual(len(truncate_text("abcdef", 5)), 5)
        with self.assertRaises(ValueError):
            truncate_text("abc", 0)

    def test_split_tags(self) -> None:
        self.assertEqual(
            split_tags("Build, test，Deploy;build； "),
            ["Build", "test", "Deploy"],
        )
        self.assertEqual(split_tags([" A ", "a", "", "B"]), ["A", "B"])
        self.assertEqual(split_tags(None), [])

    def test_normalize_keyword(self) -> None:
        self.assertEqual(normalize_keyword("  Hello  WORLD "), "hello world")
        self.assertEqual(normalize_keyword(None), "")

    def test_contains_any(self) -> None:
        self.assertTrue(contains_any("Hello Memory", ["memory"]))
        self.assertFalse(contains_any("Hello Memory", ["memory"], case_sensitive=True))
        self.assertTrue(contains_any("Hello Memory", ["Memory"], case_sensitive=True))
        self.assertFalse(contains_any(None, ["Memory"]))
        self.assertFalse(contains_any("Hello", []))
