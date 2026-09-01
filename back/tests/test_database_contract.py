"""Tests for the MySQL pilot environment contract."""

from __future__ import annotations

import pytest

from app.environment.database_contract import validate_database_contract


def _metadata(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "version": "8.4.3",
        "character_set_server": "utf8mb4",
        "character_set_database": "utf8mb4",
        "character_set_connection": "utf8mb4",
        "session_time_zone": "+00:00",
        "utc_offset_seconds": 0,
    }
    values.update(overrides)
    return values


def test_mysql_84_utf8mb4_utc_is_accepted() -> None:
    validate_database_contract(_metadata(), required_series="8.4")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"version": "8.0.42"}, "version"),
        ({"character_set_database": "utf8mb3"}, "charset"),
        ({"character_set_connection": "latin1"}, "charset"),
        ({"session_time_zone": "+08:00"}, "time zone"),
        ({"utc_offset_seconds": 28800}, "UTC offset"),
    ],
)
def test_database_contract_rejects_mismatches(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(RuntimeError, match=message):
        validate_database_contract(_metadata(**overrides), required_series="8.4")


def test_database_contract_rejects_invalid_offset_metadata() -> None:
    with pytest.raises(RuntimeError, match="UTC offset"):
        validate_database_contract(
            _metadata(utc_offset_seconds="not-a-number"),
            required_series="8.4",
        )
