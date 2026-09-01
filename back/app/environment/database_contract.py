"""Validation for the database runtime used by pilot and production."""

from __future__ import annotations

from collections.abc import Mapping


def validate_database_contract(
    metadata: Mapping[str, object], *, required_series: str
) -> None:
    """Reject a database that is outside the required MySQL/charset/UTC gate."""
    failures: list[str] = []
    version = str(metadata.get("version") or "")
    if not version.startswith(f"{required_series}."):
        failures.append(f"version must be MySQL {required_series}")

    charset_keys = (
        "character_set_server",
        "character_set_database",
        "character_set_connection",
    )
    if any(str(metadata.get(key) or "").lower() != "utf8mb4" for key in charset_keys):
        failures.append("charset must be utf8mb4")

    if str(metadata.get("session_time_zone") or "") not in {"+00:00", "UTC"}:
        failures.append("time zone must be UTC")

    try:
        offset_seconds = int(str(metadata.get("utc_offset_seconds") or 0))
    except (TypeError, ValueError):
        failures.append("UTC offset must be numeric and zero")
    else:
        if abs(offset_seconds) > 1:
            failures.append("UTC offset must be zero")

    if failures:
        raise RuntimeError("Database environment mismatch: " + "; ".join(failures))
