"""Request schemas shared by asset usage and return workflows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.schemas.fields import UTCDateTime

from marshmallow import (
    Schema,
    ValidationError,
    fields,
    pre_load,
    validate,
    validates_schema,
)


def _normalize_idempotency_key(data: Any) -> Any:
    if not isinstance(data, Mapping):
        return data
    normalized = dict(data)
    key = normalized.get("idempotency_key")
    if isinstance(key, str):
        normalized["idempotency_key"] = key.strip()
    return normalized


class _AssetCreateSchema(Schema):
    asset_ids = fields.List(
        fields.Integer(strict=True),
        required=True,
        validate=validate.Length(min=1, max=100),
    )
    idempotency_key = fields.String(
        required=False,
        allow_none=True,
        validate=validate.Length(min=1, max=191),
    )

    @pre_load
    def normalize_idempotency_key(self, data: Any, **_kwargs: Any) -> Any:
        return _normalize_idempotency_key(data)

    @validates_schema
    def validate_unique_asset_ids(self, data: dict[str, Any], **_kwargs: Any) -> None:
        asset_ids = data["asset_ids"]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValidationError("资产 ID 不能重复", field_name="asset_ids")


class PersonalUsageCreateSchema(Schema):
    asset_ids = fields.List(
        fields.Integer(strict=True),
        required=False,
        validate=validate.Length(min=1, max=100),
    )
    category_id = fields.Integer(required=False, strict=True)
    requested_quantity = fields.Integer(
        required=False,
        strict=True,
        validate=validate.Range(min=1),
    )
    target_user_id = fields.Integer(required=True, strict=True)
    location_id = fields.Integer(required=False, allow_none=True, strict=True)
    reason = fields.String(
        required=False,
        allow_none=True,
        validate=validate.Length(max=2000),
    )
    idempotency_key = fields.String(
        required=False,
        allow_none=True,
        validate=validate.Length(min=1, max=191),
    )

    @pre_load
    def normalize_idempotency_key(self, data: Any, **_kwargs: Any) -> Any:
        return _normalize_idempotency_key(data)

    @validates_schema
    def validate_asset_selection(self, data: dict[str, Any], **_kwargs: Any) -> None:
        asset_ids = data.get("asset_ids")
        category_id = data.get("category_id")
        if (asset_ids is None) == (category_id is None):
            raise ValidationError("具体资产与资产类别必须且只能选择一种")
        if asset_ids is not None:
            if len(asset_ids) != len(set(asset_ids)):
                raise ValidationError("资产 ID 不能重复", field_name="asset_ids")
            if data.get("requested_quantity") is not None:
                raise ValidationError(
                    "选择具体资产时不能填写申请数量",
                    field_name="requested_quantity",
                )
        elif data.get("requested_quantity") is None:
            raise ValidationError(
                "按资产类别申请时必须填写申请数量",
                field_name="requested_quantity",
            )


class _SelfPersonalUsageCreateSchema(Schema):
    """Employee-facing request: choose concrete assets or a category quantity."""

    asset_ids = fields.List(
        fields.Integer(strict=True),
        required=False,
        validate=validate.Length(min=1, max=100),
    )
    category_id = fields.Integer(required=False, strict=True)
    requested_quantity = fields.Integer(
        required=False,
        strict=True,
        validate=validate.Range(min=1, max=100),
    )
    location_id = fields.Integer(required=False, allow_none=True, strict=True)
    reason = fields.String(
        required=False,
        allow_none=True,
        validate=validate.Length(max=2000),
    )
    idempotency_key = fields.String(
        required=False,
        allow_none=True,
        validate=validate.Length(min=1, max=191),
    )

    @pre_load
    def normalize_strings(self, data: Any, **_kwargs: Any) -> Any:
        normalized = _normalize_idempotency_key(data)
        if not isinstance(normalized, Mapping):
            return normalized
        result = dict(normalized)
        reason = result.get("reason")
        if isinstance(reason, str):
            result["reason"] = reason.strip()
        return result

    @validates_schema
    def validate_asset_selection(self, data: dict[str, Any], **_kwargs: Any) -> None:
        asset_ids = data.get("asset_ids")
        category_id = data.get("category_id")
        if (asset_ids is None) == (category_id is None):
            raise ValidationError("具体资产与资产类别必须且只能选择一种")
        if asset_ids is not None:
            if len(asset_ids) != len(set(asset_ids)):
                raise ValidationError("资产 ID 不能重复", field_name="asset_ids")
            if data.get("requested_quantity") is not None:
                raise ValidationError(
                    "选择具体资产时不能填写申请数量",
                    field_name="requested_quantity",
                )
        elif data.get("requested_quantity") is None:
            raise ValidationError(
                "按资产类别申请时必须填写申请数量",
                field_name="requested_quantity",
            )


class SelfPersonalUsageCreateSchema(_SelfPersonalUsageCreateSchema):
    pass


class SelfPersonalBorrowCreateSchema(_SelfPersonalUsageCreateSchema):
    expected_return_at = UTCDateTime(required=True, format="iso")


class PublicUsageCreateSchema(_AssetCreateSchema):
    public_object_id = fields.Integer(required=True, strict=True)
    location_id = fields.Integer(required=True, strict=True)


class PersonalBorrowCreateSchema(PersonalUsageCreateSchema):
    expected_return_at = UTCDateTime(required=True, format="iso")

    @validates_schema
    def validate_borrow_selection(self, data: dict[str, Any], **_kwargs: Any) -> None:
        if data.get("asset_ids") is None:
            raise ValidationError("借用必须选择具体资产", field_name="asset_ids")


class PublicBorrowCreateSchema(PublicUsageCreateSchema):
    expected_return_at = UTCDateTime(required=True, format="iso")


class PersonalReturnCreateSchema(_AssetCreateSchema):
    pass


class ReturnInspectionSchema(Schema):
    asset_id = fields.Integer(required=True, strict=True)
    condition = fields.String(
        required=True,
        validate=validate.OneOf(["NORMAL", "DAMAGED"]),
    )
    condition_description = fields.String(
        required=False,
        allow_none=True,
        validate=validate.Length(max=2000),
    )

    @pre_load
    def strip_description(self, data: Any, **_kwargs: Any) -> Any:
        if not isinstance(data, Mapping):
            return data
        normalized = dict(data)
        description = normalized.get("condition_description")
        if isinstance(description, str):
            normalized["condition_description"] = description.strip()
        return normalized

    @validates_schema
    def validate_condition(self, data: dict[str, Any], **_kwargs: Any) -> None:
        description = data.get("condition_description")
        if data["condition"] == "DAMAGED":
            if not description:
                raise ValidationError(
                    "损坏资产必须填写情况说明",
                    field_name="condition_description",
                )
        else:
            data["condition_description"] = None


class _InspectionItemsSchema(Schema):
    return_company_id = fields.Integer(required=True, strict=True)
    return_usage_company_id = fields.Integer(required=True, strict=True)
    return_region_id = fields.Integer(required=True, strict=True)
    return_location_id = fields.Integer(required=True, strict=True)
    items = fields.List(
        fields.Nested(ReturnInspectionSchema),
        required=True,
        validate=validate.Length(min=1, max=100),
    )
    idempotency_key = fields.String(
        required=False,
        allow_none=True,
        validate=validate.Length(min=1, max=191),
    )

    @pre_load
    def normalize_idempotency_key(self, data: Any, **_kwargs: Any) -> Any:
        return _normalize_idempotency_key(data)

    @validates_schema
    def validate_unique_inspections(self, data: dict[str, Any], **_kwargs: Any) -> None:
        asset_ids = [item["asset_id"] for item in data["items"]]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValidationError("验收资产 ID 不能重复", field_name="items")


class PersonalDirectReturnCreateSchema(_AssetCreateSchema, _InspectionItemsSchema):
    pass


class PublicReturnCreateSchema(_AssetCreateSchema, _InspectionItemsSchema):
    pass


class ReturnConfirmSchema(_InspectionItemsSchema):
    pass


class UsageReturnPageQuerySchema(Schema):
    page = fields.Integer(load_default=0, validate=validate.Range(min=0))
    size = fields.Integer(
        load_default=50,
        validate=validate.Range(min=1, max=100),
    )


class MockFeishuActionSchema(Schema):
    action = fields.String(
        required=True,
        validate=validate.OneOf(["APPROVE", "REJECT", "WITHDRAW"]),
    )
    external_event_id = fields.String(
        required=True,
        validate=validate.Length(min=1, max=191),
    )
    reason = fields.String(
        required=False,
        allow_none=True,
        validate=validate.Length(max=2000),
    )

    @pre_load
    def strip_strings(self, data: Any, **_kwargs: Any) -> Any:
        if not isinstance(data, Mapping):
            return data
        normalized = dict(data)
        for key in ("external_event_id", "reason"):
            value = normalized.get(key)
            if isinstance(value, str):
                normalized[key] = value.strip()
        return normalized

    @validates_schema
    def validate_reason(self, data: dict[str, Any], **_kwargs: Any) -> None:
        reason = data.get("reason")
        if data["action"] == "REJECT" and not reason:
            raise ValidationError("拒绝时必须填写原因", field_name="reason")
        if not reason:
            data["reason"] = None


__all__ = [
    "BorrowReturnRequestSchema",
    "BorrowExtensionCreateSchema",
    "BorrowExtensionReviewSchema",
    "MockFeishuActionSchema",
    "PersonalBorrowCreateSchema",
    "PersonalReturnCreateSchema",
    "PersonalUsageCreateSchema",
    "PublicBorrowCreateSchema",
    "PublicReturnCreateSchema",
    "PublicUsageCreateSchema",
    "ReturnConfirmSchema",
    "ReturnHandoverSchema",
    "SelfPersonalBorrowCreateSchema",
    "SelfPersonalUsageCreateSchema",
    "ReturnInspectionSchema",
    "UsageIssueSchema",
    "UsageFulfillmentRemarkSchema",
    "UsageReturnPageQuerySchema",
    "UsageSignRefusalSchema",
]


class ReturnHandoverSchema(Schema):
    remark = fields.String(
        required=False,
        allow_none=True,
        validate=validate.Length(max=2000),
    )


class UsageIssueSchema(Schema):
    asset_ids = fields.List(
        fields.Integer(required=True, strict=True),
        required=True,
        validate=validate.Length(min=1, max=100),
    )
    region_id = fields.Integer(required=True, strict=True)
    location_id = fields.Integer(required=True, strict=True)
    remark = fields.String(
        required=False,
        allow_none=True,
        validate=validate.Length(max=2000),
    )

    @validates_schema
    def validate_unique_assets(self, data: dict[str, Any], **_kwargs: Any) -> None:
        asset_ids = data["asset_ids"]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValidationError("资产 ID 不能重复", field_name="asset_ids")


class UsageFulfillmentRemarkSchema(Schema):
    remark = fields.String(
        required=False,
        allow_none=True,
        validate=validate.Length(max=2000),
    )


class UsageSignRefusalSchema(Schema):
    remark = fields.String(
        required=True,
        validate=validate.Length(min=1, max=2000),
    )


class BorrowExtensionCreateSchema(Schema):
    requested_expected_return_at = UTCDateTime(required=True, format="iso")
    reason = fields.String(required=True, validate=validate.Length(min=2, max=2000))


class BorrowExtensionReviewSchema(Schema):
    opinion = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=2000)
    )


class BorrowReturnRequestSchema(Schema):
    reason = fields.String(
        required=True,
        validate=validate.Length(min=1, max=2000),
    )
