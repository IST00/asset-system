"""Marshmallow boundary schemas for inventory operations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from marshmallow import (
    Schema,
    ValidationError,
    fields,
    pre_load,
    validate,
    validates_schema,
)


LOSS_REASONS = (
    "NOT_WITH_ME",
    "LENT_TO_OTHERS",
    "UNDER_REPAIR",
    "TEMPORARILY_MISSING",
    "SUSPECTED_LOST",
    "OTHER",
)


class InventoryTaskPageQuerySchema(Schema):
    page = fields.Integer(load_default=0, validate=validate.Range(min=0))
    size = fields.Integer(load_default=50, validate=validate.Range(min=1, max=100))
    status = fields.String(
        required=False,
        allow_none=True,
        validate=validate.OneOf(
            ["DRAFT", "IN_PROGRESS", "OVERDUE", "REVIEWING", "COMPLETED", "CANCELLED"]
        ),
    )


class InventoryItemPageQuerySchema(Schema):
    page = fields.Integer(load_default=0, validate=validate.Range(min=0))
    size = fields.Integer(load_default=100, validate=validate.Range(min=1, max=500))
    status = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=32)
    )
    responsible_user_id = fields.Integer(required=False, allow_none=True, strict=True)


class InventoryScanEventPageQuerySchema(Schema):
    page = fields.Integer(load_default=0, validate=validate.Range(min=0))
    size = fields.Integer(load_default=100, validate=validate.Range(min=1, max=500))
    outcome = fields.String(
        required=False,
        allow_none=True,
        validate=validate.OneOf(
            [
                "MATCHED",
                "OUTSIDE_SCOPE",
                "OUTSIDE_ASSIGNMENT",
                "ALREADY_SUBMITTED",
                "UNKNOWN_ASSET",
            ]
        ),
    )


class CreateInventoryTaskSchema(Schema):
    name = fields.String(required=True, validate=validate.Length(min=2, max=255))
    deadline_at = fields.DateTime(required=True, format="iso")
    admin_user_ids = fields.List(
        fields.Integer(strict=True),
        required=True,
        validate=validate.Length(min=1, max=20),
    )
    organization_ids = fields.List(fields.Integer(strict=True), load_default=list)
    location_ids = fields.List(fields.Integer(strict=True), load_default=list)
    category_ids = fields.List(fields.Integer(strict=True), load_default=list)
    holder_user_ids = fields.List(fields.Integer(strict=True), load_default=list)
    manager_user_ids = fields.List(fields.Integer(strict=True), load_default=list)
    asset_statuses = fields.List(
        fields.String(validate=validate.OneOf(["IDLE", "IN_USE", "REPAIRING"])),
        load_default=list,
    )
    public_responsible_user_id = fields.Integer(
        required=False, allow_none=True, strict=True
    )
    photo_source_mode = fields.String(
        load_default="CAMERA_OR_ALBUM",
        validate=validate.OneOf(["CAMERA_ONLY", "CAMERA_OR_ALBUM"]),
    )
    min_photo_count = fields.Integer(load_default=1, validate=validate.OneOf([1, 2, 3]))
    publish = fields.Boolean(load_default=True)

    @pre_load
    def strip_name(self, data: Any, **_kwargs: Any) -> Any:
        if not isinstance(data, Mapping):
            return data
        normalized = dict(data)
        if isinstance(normalized.get("name"), str):
            normalized["name"] = normalized["name"].strip()
        return normalized

    @validates_schema
    def validate_unique_ids(self, data: dict[str, Any], **_kwargs: Any) -> None:
        for field_name in (
            "admin_user_ids",
            "organization_ids",
            "location_ids",
            "category_ids",
            "holder_user_ids",
            "manager_user_ids",
            "asset_statuses",
        ):
            values = data[field_name]
            if len(values) != len(set(values)):
                raise ValidationError("不能包含重复值", field_name=field_name)


class ScanInventorySchema(Schema):
    scanned_value = fields.String(
        required=True, validate=validate.Length(min=1, max=500)
    )

    @pre_load
    def strip_value(self, data: Any, **_kwargs: Any) -> Any:
        if not isinstance(data, Mapping):
            return data
        normalized = dict(data)
        if isinstance(normalized.get("scanned_value"), str):
            normalized["scanned_value"] = normalized["scanned_value"].strip()
        return normalized


class SubmitInventoryItemSchema(Schema):
    result = fields.String(required=True, validate=validate.OneOf(["FOUND", "LOSS"]))
    scanned_value = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=500)
    )
    actual_location_id = fields.Integer(required=False, allow_none=True, strict=True)
    temporary_location = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=500)
    )
    photo_ids = fields.List(
        fields.Integer(strict=True), load_default=list, validate=validate.Length(max=5)
    )
    loss_reason = fields.String(
        required=False, allow_none=True, validate=validate.OneOf(LOSS_REASONS)
    )
    loss_description = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=2000)
    )
    borrowed_by = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=128)
    )

    @pre_load
    def strip_strings(self, data: Any, **_kwargs: Any) -> Any:
        if not isinstance(data, Mapping):
            return data
        normalized = dict(data)
        for key in (
            "scanned_value",
            "temporary_location",
            "loss_description",
            "borrowed_by",
        ):
            value = normalized.get(key)
            if isinstance(value, str):
                normalized[key] = value.strip() or None
        return normalized

    @validates_schema
    def validate_result_fields(self, data: dict[str, Any], **_kwargs: Any) -> None:
        if data["result"] == "FOUND":
            if not data.get("scanned_value"):
                raise ValidationError(
                    "已找到资产必须来自真实扫码", field_name="scanned_value"
                )
            if bool(data.get("actual_location_id")) == bool(
                data.get("temporary_location")
            ):
                raise ValidationError(
                    "标准地点和临时地点必须且只能填写一个",
                    field_name="actual_location_id",
                )
            data["loss_reason"] = None
            data["loss_description"] = None
            data["borrowed_by"] = None
        else:
            if not data.get("loss_reason"):
                raise ValidationError("盘亏必须选择理由", field_name="loss_reason")
            if data["loss_reason"] == "OTHER" and not data.get("loss_description"):
                raise ValidationError(
                    "其他盘亏理由必须填写说明", field_name="loss_description"
                )
            data["actual_location_id"] = None
            data["temporary_location"] = None
            data["photo_ids"] = []


class AdminMarkInventorySchema(Schema):
    item_ids = fields.List(
        fields.Integer(strict=True),
        required=True,
        validate=validate.Length(min=1, max=500),
    )
    reason = fields.String(required=True, validate=validate.Length(min=2, max=2000))

    @validates_schema
    def validate_unique_items(self, data: dict[str, Any], **_kwargs: Any) -> None:
        if len(data["item_ids"]) != len(set(data["item_ids"])):
            raise ValidationError("盘点明细不能重复", field_name="item_ids")


class EndCollectionSchema(Schema):
    confirm_unsubmitted_count = fields.Integer(
        required=True, validate=validate.Range(min=0)
    )


class ResolveInventoryItemSchema(Schema):
    resolution = fields.String(
        required=True,
        validate=validate.OneOf(
            ["CONFIRMED_LOSS", "EXEMPTED", "KEEP_LEDGER_LOCATION", "LOCATION_RECORDED"]
        ),
    )
    reason = fields.String(required=True, validate=validate.Length(min=2, max=2000))


class ReturnInventoryItemSchema(Schema):
    reason = fields.String(required=True, validate=validate.Length(min=2, max=2000))


class CancelInventoryTaskSchema(Schema):
    reason = fields.String(required=True, validate=validate.Length(min=2, max=2000))


class ReopenInventoryItemsSchema(Schema):
    item_ids = fields.List(
        fields.Integer(strict=True),
        required=True,
        validate=validate.Length(min=1, max=500),
    )
    deadline_at = fields.DateTime(required=True, format="iso")
    reason = fields.String(required=True, validate=validate.Length(min=2, max=2000))


class UpdateInventoryAdminsSchema(Schema):
    admin_user_ids = fields.List(
        fields.Integer(strict=True),
        required=True,
        validate=validate.Length(min=1, max=20),
    )
    reason = fields.String(required=True, validate=validate.Length(min=2, max=2000))

    @validates_schema
    def validate_unique_admins(self, data: dict[str, Any], **_kwargs: Any) -> None:
        if len(data["admin_user_ids"]) != len(set(data["admin_user_ids"])):
            raise ValidationError("盘点管理员不能重复", field_name="admin_user_ids")


class UpdateInventoryDeadlineSchema(Schema):
    deadline_at = fields.DateTime(required=True, format="iso")
    reason = fields.String(required=True, validate=validate.Length(min=2, max=2000))


class WithdrawInventoryItemSchema(Schema):
    reason = fields.String(required=True, validate=validate.Length(min=2, max=2000))


class TransferInventoryResponsibilitySchema(Schema):
    responsible_user_id = fields.Integer(required=True, strict=True)
    reason = fields.String(required=True, validate=validate.Length(min=2, max=2000))


class ResolveSurplusSchema(Schema):
    resolution = fields.String(
        required=True, validate=validate.OneOf(["SURPLUS", "IGNORED"])
    )
    reason = fields.String(required=True, validate=validate.Length(min=2, max=2000))


class SendInventoryReminderSchema(Schema):
    recipient_user_ids = fields.List(
        fields.Integer(strict=True),
        load_default=list,
        validate=validate.Length(max=500),
    )
    message = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=1000)
    )


__all__ = [
    "AdminMarkInventorySchema",
    "CancelInventoryTaskSchema",
    "CreateInventoryTaskSchema",
    "EndCollectionSchema",
    "InventoryItemPageQuerySchema",
    "InventoryScanEventPageQuerySchema",
    "InventoryTaskPageQuerySchema",
    "LOSS_REASONS",
    "ReopenInventoryItemsSchema",
    "ResolveInventoryItemSchema",
    "ReturnInventoryItemSchema",
    "ResolveSurplusSchema",
    "SendInventoryReminderSchema",
    "TransferInventoryResponsibilitySchema",
    "UpdateInventoryAdminsSchema",
    "UpdateInventoryDeadlineSchema",
    "WithdrawInventoryItemSchema",
    "ScanInventorySchema",
    "SubmitInventoryItemSchema",
]
