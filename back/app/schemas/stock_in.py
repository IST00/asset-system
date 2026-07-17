"""Stock-in request schemas."""

from decimal import Decimal

from marshmallow import Schema, ValidationError, fields, validate, validates_schema

from app.enums import ApprovalStatus, ExecutionStatus


class StockInItemRequestSchema(Schema):
    asset_name = fields.String(required=True, validate=validate.Length(min=1, max=255))
    category_id = fields.Integer(required=True, strict=True)
    unit_id = fields.Integer(required=True, strict=True)
    original_amount = fields.Decimal(required=True, as_string=True, places=2)
    zero_amount_reason = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=255)
    )
    purchase_date = fields.Date(required=True)
    manager_id = fields.Integer(required=True, strict=True)
    source_id = fields.Integer(required=True, strict=True)
    location_id = fields.Integer(required=True, strict=True)
    specification_model = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=255)
    )
    serial_number = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=191)
    )
    receipt_no = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=128)
    )
    remark = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=2000)
    )

    @validates_schema
    def validate_zero_amount(self, data: dict, **_kwargs) -> None:
        if (
            data["original_amount"] == Decimal("0.00")
            and not str(data.get("zero_amount_reason") or "").strip()
        ):
            raise ValidationError(
                "零金额资产必须填写原因", field_name="zero_amount_reason"
            )


class CreateStockInRequestSchema(Schema):
    organization_id = fields.Integer(required=True, strict=True)
    remark = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=2000)
    )
    items = fields.List(
        fields.Nested(StockInItemRequestSchema),
        required=True,
        validate=validate.Length(min=1, max=100),
    )


class StockInPageQuerySchema(Schema):
    page = fields.Integer(load_default=0, validate=validate.Range(min=0))
    size = fields.Integer(load_default=50, validate=validate.Range(min=1, max=100))
    request_no = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=64)
    )
    approval_status = fields.String(
        required=False,
        allow_none=True,
        validate=validate.OneOf([item.value for item in ApprovalStatus]),
    )
    execution_status = fields.String(
        required=False,
        allow_none=True,
        validate=validate.OneOf([item.value for item in ExecutionStatus]),
    )


class ApprovalDecisionRequestSchema(Schema):
    opinion = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=2000)
    )


class RejectStockInRequestSchema(Schema):
    opinion = fields.String(required=True, validate=validate.Length(min=1, max=2000))


__all__ = [
    "ApprovalDecisionRequestSchema",
    "CreateStockInRequestSchema",
    "RejectStockInRequestSchema",
    "StockInPageQuerySchema",
    "StockInItemRequestSchema",
]
