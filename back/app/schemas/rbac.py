"""RBAC request schemas."""

from marshmallow import Schema, fields, validate


class CreateRoleRequestSchema(Schema):
    code = fields.String(required=True, validate=validate.Length(min=2, max=64))
    name = fields.String(required=True, validate=validate.Length(min=1, max=128))
    data_scope = fields.String(required=True, validate=validate.Length(min=2, max=32))


class UpdateRolePermissionsRequestSchema(Schema):
    permission_ids = fields.List(fields.Integer(strict=True), required=True)


class UpdateUserRolesRequestSchema(Schema):
    role_ids = fields.List(fields.Integer(strict=True), required=True)


class UpdateRoleRequestSchema(Schema):
    name = fields.String(required=True, validate=validate.Length(min=1, max=128))
    data_scope = fields.String(required=True, validate=validate.Length(min=2, max=32))
    enabled = fields.Boolean(required=True)
    organization_ids = fields.List(fields.Integer(strict=True), load_default=list)
    version = fields.Integer(required=True, strict=True, validate=validate.Range(min=1))


__all__ = [
    "CreateRoleRequestSchema",
    "UpdateRolePermissionsRequestSchema",
    "UpdateRoleRequestSchema",
    "UpdateUserRolesRequestSchema",
]
