"""UTC storage and API boundary contracts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from marshmallow import ValidationError

from app import create_app
from app.common.datetime import isoformat_utc, normalize_utc
from app.schemas.fields import UTCDateTime
from app.schemas.user import UserResponseSchema
from config import TestConfig


def test_naive_database_datetime_is_interpreted_as_utc() -> None:
    value = normalize_utc(datetime(2026, 8, 10, 0, 0, 0))
    assert value.tzinfo == timezone.utc
    assert isoformat_utc(value) == "2026-08-10T00:00:00Z"


def test_offset_datetime_is_converted_to_utc() -> None:
    china = timezone(timedelta(hours=8))
    value = datetime(2026, 8, 10, 8, 0, 0, tzinfo=china)
    assert isoformat_utc(value) == "2026-08-10T00:00:00Z"


def test_request_datetime_requires_an_offset() -> None:
    field = UTCDateTime()
    with pytest.raises(ValidationError, match="时区"):
        field.deserialize("2026-08-10T08:00:00")
    parsed = field.deserialize("2026-08-10T08:00:00+08:00")
    assert parsed.tzinfo == timezone.utc
    assert parsed.hour == 0


def test_flask_json_provider_emits_utc_z() -> None:
    app = create_app(TestConfig)
    with app.app_context():
        encoded = app.json.dumps({"created_at": datetime(2026, 8, 10, 0, 0, 0)})
    assert '"created_at": "2026-08-10T00:00:00Z"' in encoded


def test_user_schema_emits_utc_z() -> None:
    result = UserResponseSchema().dump(
        {
            "password_changed_at": None,
            "last_login_at": datetime(
                2026,
                8,
                10,
                8,
                tzinfo=timezone(timedelta(hours=8)),
            ),
            "created_at": datetime(2026, 8, 10, 0),
            "updated_at": datetime(2026, 8, 10, 1),
        }
    )
    assert result["last_login_at"] == "2026-08-10T00:00:00Z"
    assert result["created_at"] == "2026-08-10T00:00:00Z"
