"""Feishu native integration schemas."""

from marshmallow import Schema, fields, validate


class FeishuExchangeSchema(Schema):
    code = fields.String(required=True, validate=validate.Length(min=1, max=512))


class FeishuCallbackQuerySchema(Schema):
    code = fields.String(required=False, validate=validate.Length(min=1, max=512))
    signature = fields.String(required=False, validate=validate.Length(min=1, max=128))
    timestamp = fields.String(required=False, validate=validate.Length(min=1, max=32))
    nonce = fields.String(required=False, validate=validate.Length(min=1, max=64))


class FeishuSyncSchema(Schema):
    dry_run = fields.Boolean(load_default=False)
