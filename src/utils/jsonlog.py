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
    """递归转换任意值为 JSON 安全结构，支持 datetime、Enum、dataclass 和容器类型。"""
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
    """将数据序列化为紧凑 JSON 字符串；序列化失败时返回固定兜底 JSON。"""
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
    """构建标准化日志字典，包含时间/级别/事件/消息，并过滤 fields 中的保留字段。"""
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
    """按 level 将结构化日志记录为一行 JSON，输入为 logger、事件名和扩展字段。"""
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
    """递归压缩字典中的长文本并转为 JSON 安全值，返回处理后的新字典。"""
    def compact(value: Any) -> Any:
        """递归压缩单个值；字符串走 safe_preview，容器会逐层复制并清洗。"""
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
