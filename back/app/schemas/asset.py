"""Asset query schemas."""

from marshmallow import Schema, fields, validate


class AssetPageQuerySchema(Schema):
    page = fields.Integer(load_default=0, validate=validate.Range(min=0))
    size = fields.Integer(load_default=50, validate=validate.Range(min=1, max=100))
    asset_code = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=191)
    )
    asset_name = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=255)
    )
    serial_number = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=191)
    )


__all__ = ["AssetPageQuerySchema"]
