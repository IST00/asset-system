"""Asset maintenance, relation and lifecycle command schemas."""

from app.enums import AssetStatus, UsageType
from marshmallow import (
    Schema,
    ValidationError,
    fields,
    pre_load,
    validate,
    validates_schema,
)


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
    status = fields.String(
        required=False,
        validate=validate.OneOf([item.value for item in AssetStatus]),
    )
    usage_type = fields.String(
        required=False,
        allow_none=True,
        validate=validate.OneOf([item.value for item in UsageType]),
    )
    holder_user_id = fields.Integer(required=False, allow_none=True, strict=True)
    public_object_id = fields.Integer(required=False, allow_none=True, strict=True)
    usage_company_id = fields.Integer(required=False, strict=True)
    usage_department_id = fields.Integer(
        required=False,
        allow_none=True,
        strict=True,
    )
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


class FinancialSummaryQuerySchema(Schema):
    as_of = fields.Date(required=False)


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
    usage_company_id = fields.Integer(required=False, strict=True)
    usage_department_id = fields.Integer(
        required=False,
        allow_none=True,
        strict=True,
    )
    location_id = fields.Integer(required=False, strict=True)
    manager_id = fields.Integer(required=False, strict=True)
    holder_user_id = fields.Integer(required=False, allow_none=True, strict=True)
    public_object_id = fields.Integer(required=False, allow_none=True, strict=True)
    reason = fields.String(required=True, validate=validate.Length(min=2, max=500))

    @validates_schema
    def require_target(self, data: dict, **_kwargs) -> None:
        target_fields = {
            "organization_id",
            "usage_company_id",
            "usage_department_id",
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


class ScrapAssetItemSchema(LifecycleAssetTargetSchema):
    scrap_amount = fields.Decimal(
        required=True,
        as_string=True,
        places=2,
        validate=validate.Range(min=0),
    )
    disposition = fields.String(
        required=False,
        allow_none=True,
        load_default=None,
        validate=validate.Length(max=255),
    )
    disposition_remark = fields.String(
        required=False,
        allow_none=True,
        load_default=None,
        validate=validate.Length(max=1000),
    )
    disposal_date = fields.Date(required=True)


class ScrapAssetsSchema(Schema):
    items = fields.List(
        fields.Nested(ScrapAssetItemSchema),
        required=True,
        validate=validate.Length(min=1, max=100),
    )
    child_action = fields.String(
        load_default="BLOCK", validate=validate.OneOf(["BLOCK", "DETACH", "SCRAP"])
    )
    reason = fields.String(required=True, validate=validate.Length(min=2, max=500))
    # Legacy batch-wide fields remain load-only for one compatibility cycle.
    scrap_date = fields.Date(required=False, load_only=True)
    scrap_amount = fields.Decimal(
        required=False,
        as_string=True,
        places=2,
        validate=validate.Range(min=0),
        load_only=True,
    )
    disposition = fields.String(
        required=False,
        allow_none=True,
        validate=validate.Length(max=255),
        load_only=True,
    )

    @pre_load
    def distribute_legacy_values(self, data: dict, **_kwargs) -> dict:
        normalized = dict(data)
        items = normalized.get("items")
        if not isinstance(items, list):
            return normalized
        legacy_date = normalized.get("scrap_date")
        legacy_amount = normalized.get("scrap_amount")
        legacy_disposition = normalized.get("disposition")
        normalized["items"] = [
            {
                **item,
                **(
                    {"disposal_date": legacy_date}
                    if isinstance(item, dict)
                    and "disposal_date" not in item
                    and legacy_date is not None
                    else {}
                ),
                **(
                    {"scrap_amount": legacy_amount}
                    if isinstance(item, dict)
                    and "scrap_amount" not in item
                    and legacy_amount is not None
                    else {}
                ),
                **(
                    {"disposition": legacy_disposition}
                    if isinstance(item, dict)
                    and "disposition" not in item
                    and legacy_disposition is not None
                    else {}
                ),
            }
            if isinstance(item, dict)
            else item
            for item in items
        ]
        return normalized


class TransferHandoverSchema(Schema):
    items = fields.List(
        fields.Nested(LifecycleAssetTargetSchema),
        required=True,
        validate=validate.Length(min=1, max=100),
    )
    receiver_user_id = fields.Integer(required=False, allow_none=True, strict=True)
    outgoing_user_id = fields.Integer(required=False, allow_none=True, strict=True)
    organization_id = fields.Integer(required=False, strict=True)
    location_id = fields.Integer(required=False, strict=True)
    manager_id = fields.Integer(required=False, strict=True)
    reason = fields.String(required=False, validate=validate.Length(min=2, max=500))


class TransferHandoverClaimSchema(Schema):
    handover_token = fields.String(required=True, validate=validate.Length(equal=32))
    remark = fields.String(required=False, validate=validate.Length(min=2, max=500))


__all__ = [
    "BatchUpdateAssetRequestSchema",
    "CreatePublicUsageObjectSchema",
    "FinancialSummaryQuerySchema",
    "RelationRequestSchema",
    "RepairCompleteSchema",
    "RepairStartSchema",
    "ScrapAssetItemSchema",
    "ScrapAssetsSchema",
    "TransferAssetsSchema",
    "UpdateAssetRequestSchema",
    "UpdatePublicUsageObjectSchema",
    "TransferHandoverSchema",
    "TransferHandoverClaimSchema",
]
