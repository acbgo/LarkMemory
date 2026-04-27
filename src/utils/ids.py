from __future__ import annotations

import re
import uuid


_PREFIX_PATTERN = re.compile(r"^[a-z0-9_]+$")


def _normalize_prefix(prefix: str) -> str:
    """规范化 typed ID 前缀，返回小写前缀；空值或非法字符会抛出 ValueError。"""
    normalized = prefix.strip().lower()
    if not normalized:
        raise ValueError("prefix cannot be empty")
    if not _PREFIX_PATTERN.fullmatch(normalized):
        raise ValueError(f"invalid id prefix: {prefix!r}")
    return normalized


def new_id(prefix: str, *, size: int = 12) -> str:
    """按前缀和随机后缀长度生成 typed ID，输出形如 `prefix-random`。"""
    normalized = _normalize_prefix(prefix)
    if size <= 0:
        raise ValueError("size must be greater than 0")
    if size > 32:
        raise ValueError("size cannot exceed 32")
    return f"{normalized}-{uuid.uuid4().hex[:size]}"


def event_id() -> str:
    """生成事件 ID，返回 `evt-*` 字符串；用于 NormalizedEvent 的默认标识。"""
    return new_id("evt")


def memory_id() -> str:
    """生成记忆 ID，返回 `mem-*` 字符串；用于 MemoryCore 和领域记忆主键。"""
    return new_id("mem")


def query_id() -> str:
    """生成查询 ID，返回 `qry-*` 字符串；用于检索请求和访问记录串联。"""
    return new_id("qry")


def benchmark_run_id() -> str:
    """生成 benchmark 运行 ID，返回 `bench-*` 字符串；用于评测任务追踪。"""
    return new_id("bench")


def request_id() -> str:
    """生成请求 ID，返回 `req-*` 字符串；用于 HTTP 请求日志关联。"""
    return new_id("req")


def parse_typed_id(value: str) -> tuple[str, str]:
    """解析 typed ID 字符串，返回 `(prefix, random_part)`；格式非法时抛出 ValueError。"""
    stripped = value.strip()
    if "-" not in stripped:
        raise ValueError(f"invalid typed id: {value!r}")
    prefix, random_part = stripped.split("-", 1)
    prefix = _normalize_prefix(prefix)
    if not random_part:
        raise ValueError(f"invalid typed id: {value!r}")
    return prefix, random_part


def is_typed_id(value: str, prefix: str | None = None) -> bool:
    """判断字符串是否为合法 typed ID；可传入 prefix 限定类型，非法输入返回 False。"""
    try:
        parsed_prefix, _ = parse_typed_id(value)
        if prefix is None:
            return True
        return parsed_prefix == _normalize_prefix(prefix)
    except ValueError:
        return False
