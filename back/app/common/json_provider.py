"""Flask JSON provider that emits every datetime as a UTC instant."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from flask.json.provider import DefaultJSONProvider

from app.common.datetime import isoformat_utc


class UTCJSONProvider(DefaultJSONProvider):
    """Serialize Python datetimes as ISO 8601 UTC instead of HTTP-date text."""

    @staticmethod
    def default(value: Any) -> Any:
        if isinstance(value, datetime):
            return isoformat_utc(value)
        return DefaultJSONProvider.default(value)
