"""Employee workbench query schemas."""

from __future__ import annotations

from typing import Any

from marshmallow import (
    Schema,
    ValidationError,
    fields,
    pre_load,
    validate,
    validates_schema,
)

from app.schemas.fields import UTCDateTime


class WorkbenchPageQuerySchema(Schema):
    page = fields.Integer(load_default=0, validate=validate.Range(min=0))
    size = fields.Integer(load_default=20, validate=validate.Range(min=1, max=100))
    status = fields.String(
        required=False,
        allow_none=True,
        validate=validate.Length(max=64),
    )
    keyword = fields.String(
        required=False,
        allow_none=True,
        validate=validate.Length(max=100),
    )
    start_date = UTCDateTime(required=False, allow_none=True, format="iso")
    end_date = UTCDateTime(required=False, allow_none=True, format="iso")
    pending_only = fields.Boolean(load_default=False)

    @pre_load
    def strip_strings(self, data: Any, **_kwargs: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        for key in ("status", "keyword"):
            value = normalized.get(key)
            if isinstance(value, str):
                normalized[key] = value.strip() or None
        return normalized

    @validates_schema
    def validate_dates(self, data: dict[str, Any], **_kwargs: Any) -> None:
        start = data.get("start_date")
        end = data.get("end_date")
        if start is not None and end is not None and start > end:
            raise ValidationError("开始日期不能晚于结束日期", field_name="start_date")


__all__ = ["WorkbenchPageQuerySchema"]
