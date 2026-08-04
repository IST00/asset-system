"""Marshmallow schemas for the user domain.

Schemas are the DTO boundary — controllers accept *Request and emit *Response,
entities never cross the blueprint boundary (see docs/conventions/backend.md §1,§3).
"""

from __future__ import annotations

from marshmallow import Schema, fields, validate


class LoginRequestSchema(Schema):
    username = fields.String(required=True, validate=validate.Length(min=3, max=64))
    password = fields.String(required=True, validate=validate.Length(min=6, max=128))


class RegisterRequestSchema(Schema):
    username = fields.String(required=True, validate=validate.Length(min=3, max=64))
    password = fields.String(required=True, validate=validate.Length(min=6, max=128))
    nickname = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=64)
    )


class ChangePasswordRequestSchema(Schema):
    current_password = fields.String(
        required=True, validate=validate.Length(min=6, max=128)
    )
    new_password = fields.String(
        required=True, validate=validate.Length(min=12, max=128)
    )


class UserResponseSchema(Schema):
    id = fields.Integer()
    username = fields.String()
    nickname = fields.String(allow_none=True)
    role = fields.String(allow_none=True)
    enabled = fields.Boolean()
    must_change_password = fields.Boolean()
    password_changed_at = fields.DateTime(allow_none=True)
    last_login_at = fields.DateTime(allow_none=True)
    created_at = fields.DateTime(attribute="created_at")
    updated_at = fields.DateTime(attribute="updated_at")


class LoginResponseSchema(Schema):
    token = fields.String()
    session_expires_at = fields.DateTime()
    idle_timeout_minutes = fields.Integer()
    user = fields.Nested(UserResponseSchema)


class PageQuerySchema(Schema):
    page = fields.Integer(load_default=0, validate=validate.Range(min=0))
    size = fields.Integer(load_default=10, validate=validate.Range(min=1, max=200))


class UserPreferenceUpdateSchema(Schema):
    asset_list_columns = fields.List(
        fields.String(validate=validate.Length(min=1, max=64)),
        required=False,
        validate=validate.Length(min=1, max=32),
    )
    asset_list_page_size = fields.Integer(
        required=False, strict=True, validate=validate.OneOf([20, 50, 100])
    )
    task_notice = fields.Boolean(required=False)
    approval_notice = fields.Boolean(required=False)
    weekly_digest = fields.Boolean(required=False)
