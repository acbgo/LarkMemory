from __future__ import annotations

import re


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TAG_SPLIT = re.compile(r"[,，;；]")


def normalize_whitespace(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def clean_text(text: str | None, *, max_chars: int | None = None) -> str:
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
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than 0")
    value = text or ""
    if len(value) <= max_chars:
        return value
    if max_chars <= len(suffix):
        return value[:max_chars]
    return value[: max_chars - len(suffix)] + suffix


def safe_preview(text: str | None, *, max_chars: int = 200) -> str:
    return clean_text(text, max_chars=max_chars)


def split_tags(value: str | list[str] | None) -> list[str]:
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
    return normalize_whitespace(keyword).lower()


def contains_any(
    text: str | None,
    keywords: list[str] | tuple[str, ...],
    *,
    case_sensitive: bool = False,
) -> bool:
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
