"""Asset maintenance, relation and lifecycle command schemas."""

from marshmallow import Schema, ValidationError, fields, validate, validates_schema


class AssetChangeFieldsSchema(Schema):
    asset_name = fields.String(required=False, validate=validate.Length(min=1, max=255))
    category_id = fields.Integer(required=False, strict=True)
    unit_id = fields.Integer(required=False, allow_none=True, strict=True)
    supplier_id = fields.Integer(required=False, allow_none=True, strict=True)
    original_amount = fields.Decimal(required=False, as_string=True, places=2)
    zero_amount_reason = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=255)
    )
    purchase_date = fields.Date(required=False)
    service_life_months = fields.Integer(
        required=False, strict=True, validate=validate.Range(min=1, max=1200)
    )
    manager_id = fields.Integer(required=False, strict=True)
    source_id = fields.Integer(required=False, allow_none=True, strict=True)
    location_id = fields.Integer(required=False, allow_none=True, strict=True)
    specification_model = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=255)
    )
    serial_number = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=191)
    )
    receipt_no = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=128)
    )
    rfid_tag = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=191)
    )
    remark = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=2000)
    )


class UpdateAssetRequestSchema(AssetChangeFieldsSchema):
    version = fields.Integer(required=True, strict=True, validate=validate.Range(min=1))
    reason = fields.String(required=True, validate=validate.Length(min=2, max=500))

    @validates_schema
    def require_change(self, data: dict, **_kwargs) -> None:
        if not set(data) - {"version", "reason"}:
            raise ValidationError("至少修改一个资产字段")


class BatchAssetTargetSchema(Schema):
    asset_id = fields.Integer(required=True, strict=True)
    version = fields.Integer(required=True, strict=True, validate=validate.Range(min=1))


class BatchUpdateAssetRequestSchema(Schema):
    items = fields.List(
        fields.Nested(BatchAssetTargetSchema),
        required=True,
        validate=validate.Length(min=1, max=100),
    )
    changes = fields.Nested(AssetChangeFieldsSchema, required=True)
    reason = fields.String(required=True, validate=validate.Length(min=2, max=500))

    @validates_schema
    def require_change(self, data: dict, **_kwargs) -> None:
        if not data.get("changes"):
            raise ValidationError("至少修改一个资产字段")


class RelationRequestSchema(Schema):
    child_ids = fields.List(
        fields.Integer(strict=True),
        required=True,
        validate=validate.Length(min=1, max=100),
    )
    reason = fields.String(required=True, validate=validate.Length(min=2, max=500))


class CreatePublicUsageObjectSchema(Schema):
    name = fields.String(required=True, validate=validate.Length(min=1, max=128))


class UpdatePublicUsageObjectSchema(Schema):
    name = fields.String(required=False, validate=validate.Length(min=1, max=128))
    status = fields.String(
        required=False, validate=validate.OneOf(["ENABLED", "DISABLED"])
    )

    @validates_schema
    def require_change(self, data: dict, **_kwargs) -> None:
        if not data:
            raise ValidationError("至少修改一个字段")


class LifecycleAssetTargetSchema(Schema):
    asset_id = fields.Integer(required=True, strict=True)
    version = fields.Integer(required=True, strict=True, validate=validate.Range(min=1))


class TransferAssetsSchema(Schema):
    items = fields.List(
        fields.Nested(LifecycleAssetTargetSchema),
        required=True,
        validate=validate.Length(min=1, max=100),
    )
    organization_id = fields.Integer(required=False, strict=True)
    location_id = fields.Integer(required=False, strict=True)
    manager_id = fields.Integer(required=False, strict=True)
    holder_user_id = fields.Integer(required=False, allow_none=True, strict=True)
    public_object_id = fields.Integer(required=False, allow_none=True, strict=True)
    reason = fields.String(required=True, validate=validate.Length(min=2, max=500))

    @validates_schema
    def require_target(self, data: dict, **_kwargs) -> None:
        target_fields = {
            "organization_id",
            "location_id",
            "manager_id",
            "holder_user_id",
            "public_object_id",
        }
        if not target_fields & data.keys():
            raise ValidationError("至少填写一个调拨目标")
        if (
            data.get("holder_user_id") is not None
            and data.get("public_object_id") is not None
        ):
            raise ValidationError("个人使用人和公共使用对象不能同时填写")


class RepairStartSchema(Schema):
    items = fields.List(
        fields.Nested(LifecycleAssetTargetSchema),
        required=True,
        validate=validate.Length(min=1, max=100),
    )
    vendor = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=128)
    )
    estimated_cost = fields.Decimal(
        required=False,
        allow_none=True,
        as_string=True,
        places=2,
        validate=validate.Range(min=0),
    )
    reason = fields.String(required=True, validate=validate.Length(min=2, max=500))


class RepairCompleteSchema(Schema):
    items = fields.List(
        fields.Nested(LifecycleAssetTargetSchema),
        required=True,
        validate=validate.Length(min=1, max=100),
    )
    actual_cost = fields.Decimal(
        required=False,
        allow_none=True,
        as_string=True,
        places=2,
        validate=validate.Range(min=0),
    )
    result = fields.String(required=True, validate=validate.Length(min=2, max=500))


class ScrapAssetsSchema(Schema):
    items = fields.List(
        fields.Nested(LifecycleAssetTargetSchema),
        required=True,
        validate=validate.Length(min=1, max=100),
    )
    scrap_date = fields.Date(required=True)
    scrap_amount = fields.Decimal(
        required=True,
        as_string=True,
        places=2,
        validate=validate.Range(min=0),
    )
    child_action = fields.String(
        load_default="BLOCK", validate=validate.OneOf(["BLOCK", "DETACH", "SCRAP"])
    )
    reason = fields.String(required=True, validate=validate.Length(min=2, max=500))


__all__ = [
    "BatchUpdateAssetRequestSchema",
    "CreatePublicUsageObjectSchema",
    "RelationRequestSchema",
    "RepairCompleteSchema",
    "RepairStartSchema",
    "ScrapAssetsSchema",
    "TransferAssetsSchema",
    "UpdateAssetRequestSchema",
    "UpdatePublicUsageObjectSchema",
]
