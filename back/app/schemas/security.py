"""Security event query schemas."""

from marshmallow import Schema, fields, validate


class SecurityEventPageQuerySchema(Schema):
    page = fields.Integer(load_default=0, validate=validate.Range(min=0))
    size = fields.Integer(load_default=50, validate=validate.Range(min=1, max=100))
    event_type = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=64)
    )
    keyword = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=128)
    )


__all__ = ["SecurityEventPageQuerySchema"]
