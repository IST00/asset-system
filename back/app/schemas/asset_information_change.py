"""Schemas for independent asset information change requests."""

from marshmallow import Schema, ValidationError, fields, validate, validates_schema


class InformationChangeItemSchema(Schema):
    asset_id = fields.Integer(required=True, strict=True)
    version = fields.Integer(required=True, strict=True, validate=validate.Range(min=1))
    changes = fields.Dict(keys=fields.String(), values=fields.Raw(), required=True)

    @validates_schema
    def require_changes(self, data: dict, **_kwargs) -> None:
        if not data.get("changes"):
            raise ValidationError("每项资产至少修改一个字段")


class InformationChangeRequestSchema(Schema):
    change_type = fields.String(
        required=True, validate=validate.OneOf(["PHYSICAL", "FINANCIAL", "WARRANTY"])
    )
    items = fields.List(
        fields.Nested(InformationChangeItemSchema),
        required=True,
        validate=validate.Length(min=1, max=100),
    )
    reason = fields.String(required=True, validate=validate.Length(min=2, max=500))
    idempotency_key = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=191)
    )


class InformationChangePageSchema(Schema):
    page = fields.Integer(load_default=0, validate=validate.Range(min=0))
    size = fields.Integer(load_default=50, validate=validate.Range(min=1, max=200))
    change_type = fields.String(
        required=False, validate=validate.OneOf(["PHYSICAL", "FINANCIAL", "WARRANTY"])
    )


__all__ = [
    "InformationChangePageSchema",
    "InformationChangeRequestSchema",
]
