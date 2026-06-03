"""Marshmallow schemas for the Keke (呼噜与可可) H5 endpoints.

The H5 frontend uses `from` as a payload field; Python reserves the name,
so the schema maps the wire-level `from` <-> Python attribute `from_`.
"""

from __future__ import annotations

from marshmallow import Schema, fields, validate

_EVENT_NAMES = (
    "visit",
    "generate_start",
    "generate_success",
    "save_open",
    "save_success",
)


class TrackingEventRequestSchema(Schema):
    """Body for `POST /api/keke/track` — one analytics event."""

    event = fields.String(required=True, validate=validate.OneOf(_EVENT_NAMES))
    device_id = fields.String(required=True, validate=validate.Length(min=1, max=64))
    from_ = fields.String(
        data_key="from",
        load_default="unknown",
        validate=validate.Length(max=32),
    )
    ua = fields.String(load_default=None, validate=validate.Length(max=16), allow_none=True)
    keyword = fields.String(load_default=None, validate=validate.Length(max=40), allow_none=True)
    duration_ms = fields.Integer(load_default=None, allow_none=True)


class GenerateStoryRequestSchema(Schema):
    """Body for `POST /api/keke/story/generate`.

    Carries the same analytics fields as a tracking event so the blueprint
    can emit an implicit `generate_start` row before calling DeepSeek.
    """

    device_id = fields.String(required=True, validate=validate.Length(min=1, max=64))
    from_ = fields.String(
        data_key="from",
        load_default="unknown",
        validate=validate.Length(max=32),
    )
    ua = fields.String(load_default=None, validate=validate.Length(max=16), allow_none=True)
    keyword = fields.String(required=True, validate=validate.Length(min=1, max=100))


class GenerateStoryResponseSchema(Schema):
    """Wire shape returned inside the `data` envelope."""

    content = fields.String(required=True)
