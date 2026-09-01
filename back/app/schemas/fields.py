"""Shared Marshmallow fields for API boundary contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from marshmallow import ValidationError, fields

from app.common.datetime import isoformat_utc, normalize_utc


class UTCDateTime(fields.DateTime):
    """Require offsets on input and always serialize normalized UTC instants."""

    def _deserialize(
        self,
        value: Any,
        attr: str | None,
        data: Any,
        **kwargs: Any,
    ) -> datetime:
        parsed = super()._deserialize(value, attr, data, **kwargs)
        if not isinstance(parsed, datetime):
            raise ValidationError("时间值格式无效")
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValidationError("时间必须包含时区偏移")
        return normalize_utc(parsed)

    def _serialize(
        self,
        value: Any,
        attr: str | None,
        obj: Any,
        **kwargs: Any,
    ) -> str | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise ValidationError("时间值格式无效")
        return isoformat_utc(value)
