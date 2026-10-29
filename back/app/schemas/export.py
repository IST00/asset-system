"""Asset export job request and query schemas."""

from marshmallow import Schema, fields, validate, validates_schema, ValidationError

from app.enums import AssetDataCompleteness, AssetStatus


class AssetExportFilterSchema(Schema):
    keyword = fields.String(required=False, validate=validate.Length(max=255))
    asset_codes = fields.List(
        fields.String(validate=validate.Length(min=1, max=191)),
        required=False,
        validate=validate.Length(max=500),
    )
    company_name = fields.String(required=False, validate=validate.Length(max=255))
    category_name = fields.String(required=False, validate=validate.Length(max=255))
    status = fields.String(
        required=False, validate=validate.OneOf([item.value for item in AssetStatus])
    )
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
        validate=validate.OneOf([item.value for item in AssetDataCompleteness]),
    )


class ExportCreateSchema(Schema):
    job_type = fields.String(
        required=True,
        validate=validate.OneOf(["ASSET_CSV", "REPAIR_CSV", "SCRAP_CSV", "LABEL_PDF"]),
    )
    asset_ids = fields.List(
        fields.Integer(strict=True),
        required=False,
        validate=validate.Length(min=1, max=500),
    )
    filters = fields.Nested(AssetExportFilterSchema, required=False)

    @validates_schema
    def validate_target(self, data: dict, **_kwargs) -> None:
        if data.get("asset_ids") and data.get("filters"):
            raise ValidationError("asset_ids 和 filters 不能同时使用")
        if data.get("job_type") == "LABEL_PDF" and not data.get("asset_ids"):
            raise ValidationError("标签 PDF 必须明确选择资产")


class AssetLabelQuerySchema(Schema):
    asset_ids = fields.List(
        fields.Integer(required=True),
        required=True,
        validate=validate.Length(min=1, max=100),
    )


class AssetLabelUrlQuerySchema(Schema):
    base_url = fields.Url(
        required=False,
        allow_none=True,
        relative=True,
        validate=validate.Length(max=2048),
    )


class ExportPageQuerySchema(Schema):
    page = fields.Integer(load_default=0, validate=validate.Range(min=0))
    size = fields.Integer(load_default=20, validate=validate.Range(min=1, max=100))


__all__ = [
    "AssetExportFilterSchema",
    "AssetLabelQuerySchema",
    "ExportCreateSchema",
    "ExportPageQuerySchema",
]
