"""UTC normalization helpers for database and API boundaries."""

from __future__ import annotations

from datetime import datetime, timezone


def normalize_utc(value: datetime) -> datetime:
    """Return an aware UTC value, treating legacy naive DB values as UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def isoformat_utc(value: datetime) -> str:
    """Serialize a datetime as ISO 8601 with the canonical UTC ``Z`` suffix."""
    return normalize_utc(value).isoformat().replace("+00:00", "Z")
