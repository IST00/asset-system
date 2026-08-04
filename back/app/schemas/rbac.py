"""RBAC request schemas."""

from marshmallow import Schema, fields, validate


class CreateRoleRequestSchema(Schema):
    code = fields.String(required=True, validate=validate.Length(min=2, max=64))
    name = fields.String(required=True, validate=validate.Length(min=1, max=128))
    data_scope = fields.String(required=True, validate=validate.Length(min=2, max=32))
    reason = fields.String(
        load_default=None, allow_none=True, validate=validate.Length(min=2, max=500)
    )


class UpdateRolePermissionsRequestSchema(Schema):
    permission_ids = fields.List(fields.Integer(strict=True), required=True)
    reason = fields.String(
        load_default=None, allow_none=True, validate=validate.Length(min=2, max=500)
    )


class UpdateUserRolesRequestSchema(Schema):
    role_ids = fields.List(fields.Integer(strict=True), required=True)
    reason = fields.String(
        load_default=None, allow_none=True, validate=validate.Length(min=2, max=500)
    )


class UpdateRoleRequestSchema(Schema):
    name = fields.String(required=True, validate=validate.Length(min=1, max=128))
    data_scope = fields.String(required=True, validate=validate.Length(min=2, max=32))
    enabled = fields.Boolean(required=True)
    organization_ids = fields.List(fields.Integer(strict=True), load_default=list)
    version = fields.Integer(required=True, strict=True, validate=validate.Range(min=1))
    reason = fields.String(
        load_default=None, allow_none=True, validate=validate.Length(min=2, max=500)
    )


class DeleteRoleRequestSchema(Schema):
    version = fields.Integer(required=True, strict=True, validate=validate.Range(min=1))
    reason = fields.String(required=True, validate=validate.Length(min=2, max=500))
    confirmed = fields.Boolean(required=True, validate=validate.Equal(True))


__all__ = [
    "CreateRoleRequestSchema",
    "DeleteRoleRequestSchema",
    "UpdateRolePermissionsRequestSchema",
    "UpdateRoleRequestSchema",
    "UpdateUserRolesRequestSchema",
]
