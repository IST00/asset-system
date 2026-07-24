"""Supplier request schemas."""

from marshmallow import Schema, fields, validate


class CreateSupplierRequestSchema(Schema):
    name = fields.String(
        required=True,
        validate=validate.And(
            validate.Length(max=255),
            validate.Predicate("strip", error="供应商名称不能为空"),
        ),
    )
    unified_social_credit_code = fields.String(
        required=False,
        allow_none=True,
        validate=validate.Length(max=64),
    )
    contact_name = fields.String(
        required=False,
        allow_none=True,
        validate=validate.Length(max=128),
    )
    contact_phone = fields.String(
        required=False,
        allow_none=True,
        validate=validate.Length(max=64),
    )
    address = fields.String(
        required=False,
        allow_none=True,
        validate=validate.Length(max=500),
    )
    remark = fields.String(
        required=False,
        allow_none=True,
        validate=validate.Length(max=1000),
    )


class UpdateSupplierRequestSchema(CreateSupplierRequestSchema):
    version = fields.Integer(
        required=True,
        strict=True,
        validate=validate.Range(min=1),
    )


class SupplierVersionRequestSchema(Schema):
    version = fields.Integer(
        required=True,
        strict=True,
        validate=validate.Range(min=1),
    )


class DeleteSupplierRequestSchema(SupplierVersionRequestSchema):
    reason = fields.String(
        required=True,
        validate=validate.And(
            validate.Length(max=500),
            validate.Predicate("strip", error="删除原因不能为空"),
        ),
    )


__all__ = [
    "CreateSupplierRequestSchema",
    "DeleteSupplierRequestSchema",
    "SupplierVersionRequestSchema",
    "UpdateSupplierRequestSchema",
]
