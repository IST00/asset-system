"""Asset query and data-completion schemas."""

from marshmallow import Schema, ValidationError, fields, validate, validates_schema

from app.enums import AssetDataCompleteness


class AssetPageQuerySchema(Schema):
    page = fields.Integer(load_default=0, validate=validate.Range(min=0))
    size = fields.Integer(load_default=50, validate=validate.Range(min=1, max=100))
    keyword = fields.String(required=False, validate=validate.Length(max=255))
    asset_code = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=191)
    )
    asset_codes = fields.String(required=False, validate=validate.Length(max=4000))
    asset_name = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=255)
    )
    serial_number = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=191)
    )
    company_name = fields.String(required=False, validate=validate.Length(max=255))
    category_name = fields.String(required=False, validate=validate.Length(max=255))
    status = fields.String(required=False, validate=validate.Length(max=32))
    department_name = fields.String(required=False, validate=validate.Length(max=255))
    location_name = fields.String(required=False, validate=validate.Length(max=255))
    user_name = fields.String(required=False, validate=validate.Length(max=255))
    manager_name = fields.String(required=False, validate=validate.Length(max=255))
    supplier_name = fields.String(required=False, validate=validate.Length(max=255))
    source_name = fields.String(required=False, validate=validate.Length(max=255))
    purchase_date_from = fields.Date(required=False)
    purchase_date_to = fields.Date(required=False)
    data_completeness = fields.String(
        required=False,
        allow_none=True,
        validate=validate.OneOf([item.value for item in AssetDataCompleteness]),
    )


class _CompletionFieldsSchema(Schema):
    unit_id = fields.Integer(required=False, allow_none=False, strict=True)
    source_id = fields.Integer(required=False, allow_none=False, strict=True)
    location_id = fields.Integer(required=False, allow_none=False, strict=True)

    @validates_schema
    def require_change(self, data: dict, **_kwargs) -> None:
        if not {"unit_id", "source_id", "location_id"} & data.keys():
            raise ValidationError("至少填写一个待补充字段")


class CompleteAssetDataRequestSchema(_CompletionFieldsSchema):
    version = fields.Integer(
        required=True,
        strict=True,
        validate=validate.Range(min=1),
    )


class AssetVersionTargetSchema(Schema):
    asset_id = fields.Integer(required=True, strict=True)
    version = fields.Integer(
        required=True,
        strict=True,
        validate=validate.Range(min=1),
    )


class BatchCompleteAssetDataRequestSchema(_CompletionFieldsSchema):
    items = fields.List(
        fields.Nested(AssetVersionTargetSchema),
        required=True,
        validate=validate.Length(min=1, max=100),
    )


__all__ = [
    "AssetPageQuerySchema",
    "AssetVersionTargetSchema",
    "BatchCompleteAssetDataRequestSchema",
    "CompleteAssetDataRequestSchema",
]
