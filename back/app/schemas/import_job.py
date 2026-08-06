"""Import-center request schemas."""

from marshmallow import Schema, fields, validate

_IMPORT_TYPES = ("ASSET", "ORGANIZATION", "CATEGORY")


class ImportPreviewRequestSchema(Schema):
    import_type = fields.String(required=True, validate=validate.OneOf(_IMPORT_TYPES))


class ImportConfirmRequestSchema(Schema):
    confirmed = fields.Boolean(required=True, validate=validate.Equal(True))
    version = fields.Integer(required=True, strict=True, validate=validate.Range(min=1))


class ImportPageQuerySchema(Schema):
    page = fields.Integer(load_default=0, validate=validate.Range(min=0))
    size = fields.Integer(load_default=20, validate=validate.Range(min=1, max=100))
    import_type = fields.String(
        required=False, allow_none=True, validate=validate.OneOf(_IMPORT_TYPES)
    )
    status = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=32)
    )


__all__ = [
    "ImportConfirmRequestSchema",
    "ImportPageQuerySchema",
    "ImportPreviewRequestSchema",
]
