from __future__ import annotations

import dataclasses
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any

from .text import safe_preview
from .time import format_iso, utc_now_iso


_RESERVED_FIELDS = {"timestamp", "level", "event", "message"}


def json_safe(value: Any) -> Any:
    """将对象递归转换为可 JSON 序列化的安全结构。"""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        return format_iso(value)
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return json_safe(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return str(value)


def json_dumps(data: Any) -> str:
    """将数据序列化为紧凑 JSON 字符串，失败时返回兜底结果。"""
    try:
        return json.dumps(
            json_safe(data),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    except Exception:
        return json.dumps(
            {"message": "<unserializable>"},
            ensure_ascii=False,
            separators=(",", ":"),
        )


def json_log_record(
    event: str,
    *,
    level: str = "INFO",
    message: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """构建标准化 JSON 日志记录并过滤保留字段冲突。"""
    record = {
        "timestamp": utc_now_iso(),
        "level": level.upper(),
        "event": event,
        "message": message,
    }
    safe_fields = json_safe(fields)
    for key, value in safe_fields.items():
        if key in _RESERVED_FIELDS:
            continue
        record[key] = value
    return record


def log_json(
    logger: logging.Logger,
    event: str,
    *,
    level: str = "INFO",
    message: str | None = None,
    **fields: Any,
) -> None:
    """按日志级别将结构化日志以 JSON 形式写入 logger。"""
    payload = json_dumps(
        json_log_record(event, level=level, message=message, **fields)
    )
    method_name = level.lower()
    if method_name == "warn":
        method_name = "warning"
    if method_name not in {"debug", "info", "warning", "error", "critical"}:
        method_name = "info"
    getattr(logger, method_name)(payload)


def compact_dict(
    data: dict[str, Any],
    *,
    max_text_chars: int = 500,
) -> dict[str, Any]:
    """压缩字典中的长文本字段并递归清洗为 JSON 安全值。"""
    def compact(value: Any) -> Any:
        """递归压缩单个值，处理文本、容器和基础类型。"""
        if isinstance(value, str):
            return safe_preview(value, max_chars=max_text_chars)
        if isinstance(value, dict):
            return {str(key): compact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [compact(item) for item in value]
        if isinstance(value, tuple):
            return [compact(item) for item in value]
        if isinstance(value, set):
            return [compact(item) for item in value]
        return json_safe(value)

    return {str(key): compact(value) for key, value in data.items()}
