from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ChunkResult:
    """单个文本片段，可直接映射到 NormalizedEvent 的 title/content_text。"""

    chunk_id: str
    content: str
    heading: str | None = None
    heading_level: int = 0
    index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


def _make_chunk_id(prefix: str, index: int, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{index:03d}-{digest}"


def split_by_headings(markdown_text: str) -> list[ChunkResult]:
    """按 Markdown H1/H2 标题切分文本，每个标题段落为一个 ChunkResult。

    标题行前的文本作为 preamble（heading=None, heading_level=0）。
    返回值按原文顺序排列，chunk_id 以 'h' 为前缀。
    """
    if not markdown_text.strip():
        return []

    heading_re = re.compile(r"^(#{1,2})\s+(.+)$", re.MULTILINE)
    matches = list(heading_re.finditer(markdown_text))

    if not matches:
        return [ChunkResult(
            chunk_id=_make_chunk_id("h", 0, markdown_text),
            content=markdown_text.strip(),
            index=0,
        )]

    chunks: list[ChunkResult] = []
    idx = 0

    # preamble: 第一个标题之前的内容
    first_pos = matches[0].start()
    if first_pos > 0:
        preamble = markdown_text[:first_pos].strip()
        if preamble:
            chunks.append(ChunkResult(
                chunk_id=_make_chunk_id("h", idx, preamble),
                content=preamble,
                index=idx,
            ))
            idx += 1

    for i, match in enumerate(matches):
        heading_level = len(match.group(1))
        heading_text = match.group(2).strip()
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown_text)
        body = markdown_text[body_start:body_end].strip()
        full_content = f"{'#' * heading_level} {heading_text}\n{body}" if body else f"{'#' * heading_level} {heading_text}"
        chunks.append(ChunkResult(
            chunk_id=_make_chunk_id("h", idx, full_content),
            content=full_content,
            heading=heading_text,
            heading_level=heading_level,
            index=idx,
            metadata={"heading_raw": match.group(0).strip()},
        ))
        idx += 1

    return chunks


def split_by_chapters(
    verbatim_text: str, chapters: list[dict[str, Any]]
) -> list[ChunkResult]:
    """按妙记 AI 章节切分逐字稿，每章为一个 ChunkResult。

    chapters 列表每项应包含 title(str) 和 start_time_ms(int) 字段。
    逐字稿按章段时间戳边界切分，超出最后一个章节的尾部内容作为独立 chunk。
    chunk_id 以 'ch' 为前缀。
    """
    if not verbatim_text.strip():
        return []

    if not chapters:
        return [ChunkResult(
            chunk_id=_make_chunk_id("ch", 0, verbatim_text),
            content=verbatim_text.strip(),
            heading="全文",
            index=0,
        )]

    chunks: list[ChunkResult] = []
    lines = verbatim_text.split("\n")

    # 从逐字稿行中提取时间戳（格式如 [00:01:23] 或 (00:01:23)）
    ts_re = re.compile(r"[\[\(](\d{2}):(\d{2}):(\d{2})[\]\)]")

    def _line_to_ms(line: str) -> int | None:
        m = ts_re.search(line)
        if m:
            return int(m.group(1)) * 3600000 + int(m.group(2)) * 60000 + int(m.group(3)) * 1000
        return None

    chapter_boundaries: list[int] = []
    for ch in chapters:
        start_ms = ch.get("start_time_ms", 0)
        if isinstance(start_ms, (int, float)) and start_ms >= 0:
            chapter_boundaries.append(int(start_ms))
        else:
            chapter_boundaries.append(0)

    # 按章段时间边界分配行
    current_chapter_idx = 0
    chapter_buckets: list[list[str]] = [[] for _ in chapters]
    tail_bucket: list[str] = []

    for line in lines:
        line_ms = _line_to_ms(line)
        if line_ms is not None:
            while current_chapter_idx + 1 < len(chapter_boundaries) and line_ms >= chapter_boundaries[current_chapter_idx + 1]:
                current_chapter_idx += 1
        if current_chapter_idx < len(chapter_buckets):
            chapter_buckets[current_chapter_idx].append(line)
        else:
            tail_bucket.append(line)

    for i, (ch, bucket) in enumerate(zip(chapters, chapter_buckets)):
        content = "\n".join(bucket).strip()
        if not content:
            continue
        heading = ch.get("title", f"章节 {i+1}")
        chunks.append(ChunkResult(
            chunk_id=_make_chunk_id("ch", i, content),
            content=content,
            heading=heading,
            heading_level=1,
            index=i,
            metadata={"chapter_title": heading, "start_time_ms": chapter_boundaries[i]},
        ))

    if tail_bucket:
        tail_content = "\n".join(tail_bucket).strip()
        if tail_content:
            chunks.append(ChunkResult(
                chunk_id=_make_chunk_id("ch", len(chapters), tail_content),
                content=tail_content,
                heading="尾部",
                index=len(chapters),
            ))

    return chunks
