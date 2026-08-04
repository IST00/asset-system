"""Request schemas for asset attachments."""

from marshmallow import Schema, fields, validate


_ATTACHMENT_TYPES = (
    "PHOTO",
    "CONTRACT",
    "INVOICE",
    "ACCEPTANCE",
    "REPAIR",
    "SCRAP",
    "OTHER",
)


class AttachmentUploadSchema(Schema):
    business_type = fields.String(
        required=True, validate=validate.OneOf(_ATTACHMENT_TYPES)
    )


class AttachmentVoidSchema(Schema):
    reason = fields.String(required=True, validate=validate.Length(min=2, max=500))
    version = fields.Integer(required=True, strict=True, validate=validate.Range(min=1))


class AttachmentCoverSchema(Schema):
    version = fields.Integer(required=True, strict=True, validate=validate.Range(min=1))


__all__ = [
    "AttachmentCoverSchema",
    "AttachmentUploadSchema",
    "AttachmentVoidSchema",
]
