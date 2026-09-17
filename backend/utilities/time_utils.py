from __future__ import annotations

from datetime import UTC, date, datetime, time


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    """Return an aware UTC datetime, treating SQLite's naive values as UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def day_bounds(value: date) -> tuple[datetime, datetime]:
    return datetime.combine(value, time.min, tzinfo=UTC), datetime.combine(value, time.max, tzinfo=UTC)


def seconds_between(start: datetime | None, end: datetime | None) -> float | None:
    return max(0.0, (ensure_utc(end) - ensure_utc(start)).total_seconds()) if start and end else None
