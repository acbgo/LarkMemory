from __future__ import annotations

from datetime import datetime, timedelta, timezone


def utc_now() -> datetime:
    """返回当前 UTC 时区的时间（带时区信息）。"""
    return datetime.now(timezone.utc)


def to_utc(dt: datetime) -> datetime:
    """将时间统一转换为 UTC；若无时区则按 UTC 处理。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_iso(dt: datetime | None = None) -> str:
    """将时间格式化为以 Z 结尾的 ISO-8601 字符串。"""
    value = to_utc(dt or utc_now())
    return value.isoformat().replace("+00:00", "Z")


def utc_now_iso() -> str:
    """返回当前 UTC 时间的 ISO-8601 字符串。"""
    return format_iso(utc_now())


def parse_iso(value: str) -> datetime:
    """解析 ISO-8601 字符串并返回 UTC 时间。"""
    stripped = value.strip()
    if not stripped:
        raise ValueError("cannot parse empty ISO datetime")
    normalized = stripped[:-1] + "+00:00" if stripped.endswith("Z") else stripped
    try:
        return to_utc(datetime.fromisoformat(normalized))
    except ValueError as exc:
        raise ValueError(f"invalid ISO datetime: {value!r}") from exc


def _coerce_datetime(value: datetime | str) -> datetime:
    """将 datetime 或时间字符串统一转换为 UTC datetime。"""
    if isinstance(value, datetime):
        return to_utc(value)
    return parse_iso(value)


def add_duration(dt: datetime | str, **kwargs: int) -> datetime:
    """为给定时间增加指定时长并返回新时间。"""
    return _coerce_datetime(dt) + timedelta(**kwargs)


def time_window(
    reference: datetime | str | None = None,
    *,
    days: int = 0,
    hours: int = 0,
    minutes: int = 0,
) -> tuple[str, str]:
    """按给定时长生成 [start, end] 的 UTC ISO 时间窗口。"""
    if days <= 0 and hours <= 0 and minutes <= 0:
        raise ValueError("time window duration must be greater than 0")
    end = _coerce_datetime(reference) if reference is not None else utc_now()
    start = end - timedelta(days=days, hours=hours, minutes=minutes)
    return format_iso(start), format_iso(end)


def is_expired(
    valid_to: str | datetime | None,
    *,
    now: datetime | None = None,
) -> bool:
    """判断有效期截止时间是否早于当前时间。"""
    if valid_to is None:
        return False
    valid_to_dt = _coerce_datetime(valid_to)
    now_dt = to_utc(now or utc_now())
    return valid_to_dt < now_dt


def days_between(start: str | datetime, end: str | datetime | None = None) -> float:
    """计算两个时间点之间相差的天数（可为小数）。"""
    start_dt = _coerce_datetime(start)
    end_dt = _coerce_datetime(end) if end is not None else utc_now()
    return (end_dt - start_dt).total_seconds() / 86400
