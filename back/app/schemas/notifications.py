"""Notification inbox query schemas."""

from marshmallow import Schema, fields, validate


class NotificationPageQuerySchema(Schema):
    page = fields.Integer(load_default=0, validate=validate.Range(min=0))
    size = fields.Integer(load_default=20, validate=validate.Range(min=1, max=100))
    unread_only = fields.Boolean(load_default=False)


class NotificationReadAllSchema(Schema):
    confirm = fields.Boolean(load_default=True)
