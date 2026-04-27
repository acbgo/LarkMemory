from __future__ import annotations

from datetime import datetime, timedelta, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_iso(dt: datetime | None = None) -> str:
    value = to_utc(dt or utc_now())
    return value.isoformat().replace("+00:00", "Z")


def utc_now_iso() -> str:
    return format_iso(utc_now())


def parse_iso(value: str) -> datetime:
    stripped = value.strip()
    if not stripped:
        raise ValueError("cannot parse empty ISO datetime")
    normalized = stripped[:-1] + "+00:00" if stripped.endswith("Z") else stripped
    try:
        return to_utc(datetime.fromisoformat(normalized))
    except ValueError as exc:
        raise ValueError(f"invalid ISO datetime: {value!r}") from exc


def _coerce_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return to_utc(value)
    return parse_iso(value)


def add_duration(dt: datetime | str, **kwargs: int) -> datetime:
    return _coerce_datetime(dt) + timedelta(**kwargs)


def time_window(
    reference: datetime | str | None = None,
    *,
    days: int = 0,
    hours: int = 0,
    minutes: int = 0,
) -> tuple[str, str]:
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
    if valid_to is None:
        return False
    valid_to_dt = _coerce_datetime(valid_to)
    now_dt = to_utc(now or utc_now())
    return valid_to_dt < now_dt


def days_between(start: str | datetime, end: str | datetime | None = None) -> float:
    start_dt = _coerce_datetime(start)
    end_dt = _coerce_datetime(end) if end is not None else utc_now()
    return (end_dt - start_dt).total_seconds() / 86400
