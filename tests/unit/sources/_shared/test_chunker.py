from __future__ import annotations

import unittest

from src.sources._shared.chunker import ChunkResult, split_by_headings, split_by_chapters


class TestSplitByHeadings(unittest.TestCase):

    def test_empty_text(self) -> None:
        self.assertEqual(split_by_headings(""), [])
        self.assertEqual(split_by_headings("   \n  "), [])

    def test_no_headings_returns_single_chunk(self) -> None:
        text = "这是一段普通文本，没有任何标题。\n第二行内容。"
        results = split_by_headings(text)
        self.assertEqual(len(results), 1)
        self.assertIsNone(results[0].heading)
        self.assertEqual(results[0].heading_level, 0)
        self.assertIn("普通文本", results[0].content)

    def test_single_h1(self) -> None:
        text = "# 项目概述\n\n这里是项目概述的正文内容。"
        results = split_by_headings(text)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].heading, "项目概述")
        self.assertEqual(results[0].heading_level, 1)

    def test_single_h2(self) -> None:
        text = "## 技术选型\n\n后端使用 Python，前端使用 React。"
        results = split_by_headings(text)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].heading, "技术选型")
        self.assertEqual(results[0].heading_level, 2)

    def test_preamble_before_first_heading(self) -> None:
        text = "这是前言内容。\n\n# 第一章\n\n第一章正文。"
        results = split_by_headings(text)
        self.assertEqual(len(results), 2)
        self.assertIsNone(results[0].heading)
        self.assertIn("前言", results[0].content)
        self.assertEqual(results[1].heading, "第一章")

    def test_multiple_h1_and_h2(self) -> None:
        text = (
            "# 架构设计\n\n架构正文。\n\n"
            "## 存储层\n\n存储层正文。\n\n"
            "## 检索层\n\n检索层正文。\n\n"
            "# 部署方案\n\n部署正文。"
        )
        results = split_by_headings(text)
        self.assertEqual(len(results), 4)
        self.assertEqual(results[0].heading, "架构设计")
        self.assertEqual(results[0].heading_level, 1)
        self.assertEqual(results[1].heading, "存储层")
        self.assertEqual(results[1].heading_level, 2)
        self.assertEqual(results[2].heading, "检索层")
        self.assertEqual(results[2].heading_level, 2)
        self.assertEqual(results[3].heading, "部署方案")
        self.assertEqual(results[3].heading_level, 1)

    def test_ignores_h3_and_deeper(self) -> None:
        text = "# 主标题\n\n### 三级标题\n这个 h3 不会触发新 chunk。"
        results = split_by_headings(text)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].heading, "主标题")
        self.assertIn("### 三级标题", results[0].content)

    def test_chunk_id_uniqueness(self) -> None:
        text = "# A\n\n内容 A\n\n# B\n\n内容 B"
        results = split_by_headings(text)
        ids = [r.chunk_id for r in results]
        self.assertEqual(len(ids), len(set(ids)))

    def test_empty_heading_content(self) -> None:
        text = "# 仅标题"
        results = split_by_headings(text)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].heading, "仅标题")
        self.assertIn("# 仅标题", results[0].content)

    def test_headings_with_special_characters(self) -> None:
        text = "# 需求-评审_2026\n\n正文\n\n## API v2.0 (新版)"
        results = split_by_headings(text)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].heading, "需求-评审_2026")
        self.assertEqual(results[1].heading, "API v2.0 (新版)")


class TestSplitByChapters(unittest.TestCase):

    def test_empty_text(self) -> None:
        self.assertEqual(split_by_chapters("", []), [])
        self.assertEqual(split_by_chapters("   ", []), [])

    def test_no_chapters_returns_full_text(self) -> None:
        text = "00:00:01 大家好\n00:00:05 今天讨论项目进度"
        results = split_by_chapters(text, [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].heading, "全文")
        self.assertIn("项目进度", results[0].content)

    def test_single_chapter_covers_all(self) -> None:
        chapters = [{"title": "开场", "start_time_ms": 0}]
        text = "[00:00:01] 大家好\n[00:00:30] 开始讨论"
        results = split_by_chapters(text, chapters)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].heading, "开场")
        self.assertIn("大家好", results[0].content)
        self.assertIn("开始讨论", results[0].content)

    def test_two_chapters_split_at_boundary(self) -> None:
        chapters = [
            {"title": "项目进展", "start_time_ms": 0},
            {"title": "技术讨论", "start_time_ms": 5000},
        ]
        text = "[00:00:01] 进展第一条\n[00:00:03] 进展第二条\n[00:00:05] 技术第一条\n[00:00:08] 技术第二条"
        results = split_by_chapters(text, chapters)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].heading, "项目进展")
        self.assertIn("进展第一条", results[0].content)
        self.assertIn("进展第二条", results[0].content)
        self.assertEqual(results[1].heading, "技术讨论")
        self.assertIn("技术第一条", results[1].content)
        self.assertIn("技术第二条", results[1].content)

    def test_empty_chapter_bucket_skipped(self) -> None:
        chapters = [
            {"title": "空章节", "start_time_ms": 0},
            {"title": "有内容", "start_time_ms": 1000},
        ]
        text = "[00:00:02] 第二章节的内容"
        results = split_by_chapters(text, chapters)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].heading, "有内容")

    def test_tail_content_after_last_chapter(self) -> None:
        chapters = [{"title": "总结", "start_time_ms": 0}]
        text = "[00:00:01] 总结内容\n[00:01:00] 这个没有对应章节的时间"
        results = split_by_chapters(text, chapters)
        self.assertEqual(len(results), 1)

    def test_chunk_id_prefix(self) -> None:
        chapters = [{"title": "测试", "start_time_ms": 0}]
        text = "[00:00:01] test"
        results = split_by_chapters(text, chapters)
        self.assertTrue(results[0].chunk_id.startswith("ch-"))

    def test_lines_without_timestamps_follow_previous(self) -> None:
        chapters = [
            {"title": "第一章", "start_time_ms": 0},
            {"title": "第二章", "start_time_ms": 10000},
        ]
        text = "[00:00:01] 第一句\n没有时间戳的行\n[00:00:10] 第二句"
        results = split_by_chapters(text, chapters)
        self.assertEqual(len(results), 2)
        # 没有时间戳的行应该跟在第一章
        self.assertIn("没有时间戳的行", results[0].content)
        # 第二章的行
        self.assertIn("第二句", results[1].content)

    def test_metadata_includes_chapter_info(self) -> None:
        chapters = [{"title": "设计评审", "start_time_ms": 60000}]
        text = "[00:01:00] 评审内容"
        results = split_by_chapters(text, chapters)
        self.assertEqual(results[0].metadata["chapter_title"], "设计评审")
        self.assertEqual(results[0].metadata["start_time_ms"], 60000)
