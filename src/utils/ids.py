from __future__ import annotations

import re
import uuid


_PREFIX_PATTERN = re.compile(r"^[a-z0-9_]+$")


def _normalize_prefix(prefix: str) -> str:
    """规范化并校验 ID 前缀格式。"""
    normalized = prefix.strip().lower()
    if not normalized:
        raise ValueError("prefix cannot be empty")
    if not _PREFIX_PATTERN.fullmatch(normalized):
        raise ValueError(f"invalid id prefix: {prefix!r}")
    return normalized


def new_id(prefix: str, *, size: int = 12) -> str:
    """按前缀生成指定长度随机后缀的 typed ID。"""
    normalized = _normalize_prefix(prefix)
    if size <= 0:
        raise ValueError("size must be greater than 0")
    if size > 32:
        raise ValueError("size cannot exceed 32")
    return f"{normalized}-{uuid.uuid4().hex[:size]}"


def event_id() -> str:
    """生成事件类型 ID。"""
    return new_id("evt")


def memory_id() -> str:
    """生成记忆类型 ID。"""
    return new_id("mem")


def query_id() -> str:
    """生成查询类型 ID。"""
    return new_id("qry")


def benchmark_run_id() -> str:
    """生成评测运行类型 ID。"""
    return new_id("bench")


def request_id() -> str:
    """生成请求类型 ID。"""
    return new_id("req")


def parse_typed_id(value: str) -> tuple[str, str]:
    """解析 typed ID，返回前缀与随机部分。"""
    stripped = value.strip()
    if "-" not in stripped:
        raise ValueError(f"invalid typed id: {value!r}")
    prefix, random_part = stripped.split("-", 1)
    prefix = _normalize_prefix(prefix)
    if not random_part:
        raise ValueError(f"invalid typed id: {value!r}")
    return prefix, random_part


def is_typed_id(value: str, prefix: str | None = None) -> bool:
    """判断字符串是否为合法 typed ID，并可限定前缀。"""
    try:
        parsed_prefix, _ = parse_typed_id(value)
        if prefix is None:
            return True
        return parsed_prefix == _normalize_prefix(prefix)
    except ValueError:
        return False
