from __future__ import annotations

import re


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TAG_SPLIT = re.compile(r"[,，;；]")


def normalize_whitespace(text: str | None) -> str:
    """折叠文本中的连续空白并去除首尾空格；None 或空字符串返回空字符串。"""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def clean_text(text: str | None, *, max_chars: int | None = None) -> str:
    """移除控制字符、规范空白并可按 max_chars 裁剪；max_chars 非正时抛出 ValueError。"""
    if max_chars is not None and max_chars <= 0:
        raise ValueError("max_chars must be greater than 0")
    cleaned = normalize_whitespace(_CONTROL_CHARS.sub("", text or ""))
    if max_chars is not None:
        return truncate_text(cleaned, max_chars)
    return cleaned


def truncate_text(
    text: str | None,
    max_chars: int,
    *,
    suffix: str = "...",
) -> str:
    """将文本截断到 max_chars 长度并按需追加 suffix；输入 None 按空字符串处理。"""
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than 0")
    value = text or ""
    if len(value) <= max_chars:
        return value
    if max_chars <= len(suffix):
        return value[:max_chars]
    return value[: max_chars - len(suffix)] + suffix


def safe_preview(text: str | None, *, max_chars: int = 200) -> str:
    """生成适合日志或界面展示的短文本预览；输出经过控制字符清理和长度限制。"""
    return clean_text(text, max_chars=max_chars)


def split_tags(value: str | list[str] | None) -> list[str]:
    """从字符串或列表生成标签列表，按中英文分隔符拆分并大小写不敏感去重。"""
    if value is None:
        return []
    raw_tags = _TAG_SPLIT.split(value) if isinstance(value, str) else value
    seen: set[str] = set()
    result: list[str] = []
    for tag in raw_tags:
        normalized = normalize_whitespace(tag)
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def normalize_keyword(keyword: str | None) -> str:
    """规范化关键词，输出折叠空白后的小写字符串；None 会返回空字符串。"""
    return normalize_whitespace(keyword).lower()


def contains_any(
    text: str | None,
    keywords: list[str] | tuple[str, ...],
    *,
    case_sensitive: bool = False,
) -> bool:
    """判断 text 是否包含任一 keyword；默认大小写不敏感，空文本或空关键词列表返回 False。"""
    if not text or not keywords:
        return False
    haystack = text if case_sensitive else text.lower()
    for keyword in keywords:
        if not keyword:
            continue
        needle = keyword if case_sensitive else keyword.lower()
        if needle in haystack:
            return True
    return False
