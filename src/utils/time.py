from __future__ import annotations

from datetime import datetime, timedelta, timezone


def utc_now() -> datetime:
    """返回当前带 timezone.utc 的 datetime。"""
    return datetime.now(timezone.utc)


def to_utc(dt: datetime) -> datetime:
    """将 datetime 转为 UTC；无时区输入按 UTC 解释，返回带时区的新 datetime。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_iso(dt: datetime | None = None) -> str:
    """将 datetime 格式化为 Z 结尾 ISO 字符串；未传入时使用当前 UTC 时间。"""
    value = to_utc(dt or utc_now())
    return value.isoformat().replace("+00:00", "Z")


def utc_now_iso() -> str:
    """返回当前 UTC 时间的 Z 结尾 ISO 字符串。"""
    return format_iso(utc_now())


def parse_iso(value: str) -> datetime:
    """解析 ISO-8601 字符串并返回 UTC datetime；空字符串或非法格式抛出 ValueError。"""
    stripped = value.strip()
    if not stripped:
        raise ValueError("cannot parse empty ISO datetime")
    normalized = stripped[:-1] + "+00:00" if stripped.endswith("Z") else stripped
    try:
        return to_utc(datetime.fromisoformat(normalized))
    except ValueError as exc:
        raise ValueError(f"invalid ISO datetime: {value!r}") from exc


def _coerce_datetime(value: datetime | str) -> datetime:
    """把 datetime 或 ISO 字符串统一转换为 UTC datetime；字符串解析失败会抛出 ValueError。"""
    if isinstance(value, datetime):
        return to_utc(value)
    return parse_iso(value)


def add_duration(dt: datetime | str, **kwargs: int) -> datetime:
    """为给定时间增加 timedelta 参数指定的时长，返回新的 UTC datetime。"""
    return _coerce_datetime(dt) + timedelta(**kwargs)


def time_window(
    reference: datetime | str | None = None,
    *,
    days: int = 0,
    hours: int = 0,
    minutes: int = 0,
) -> tuple[str, str]:
    """按 reference 和时长生成 `(start, end)` UTC ISO 窗口；未提供正向时长会抛出 ValueError。"""
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
    """判断 valid_to 是否已早于 now；valid_to 为 None 时返回 False，字符串会按 ISO 解析。"""
    if valid_to is None:
        return False
    valid_to_dt = _coerce_datetime(valid_to)
    now_dt = to_utc(now or utc_now())
    return valid_to_dt < now_dt


def days_between(start: str | datetime, end: str | datetime | None = None) -> float:
    """计算 start 到 end 的天数差并返回浮点数；end 缺省时使用当前 UTC 时间。"""
    start_dt = _coerce_datetime(start)
    end_dt = _coerce_datetime(end) if end is not None else utc_now()
    return (end_dt - start_dt).total_seconds() / 86400
