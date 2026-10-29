"""Request schemas for asset attachments."""

from marshmallow import Schema, ValidationError, fields, validate, validates_schema


_ATTACHMENT_TYPES = (
    "PHOTO",
    "CONTRACT",
    "INVOICE",
    "ACCEPTANCE",
    "REPAIR",
    "SCRAP",
    "USAGE_SIGN",
    "RETURN_HANDOVER",
    "RETURN_INSPECTION",
    "TRANSFER_RECEIPT",
    "OTHER",
)
_DOCUMENT_TYPES = (
    "ASSET_PHOTO",
    "CONTRACT",
    "INVOICE",
    "ACCEPTANCE",
    "REPAIR_PHOTO",
    "REPAIR_QUOTE",
    "REPAIR_INVOICE",
    "SCRAP_CERTIFICATE",
    "DISPOSAL_VOUCHER",
    "SIGN_PHOTO",
    "RETURN_PHOTO",
    "INSPECTION_PHOTO",
    "TRANSFER_RECEIPT_PHOTO",
    "ELECTRONIC_SIGNATURE",
    "OTHER",
)


class AttachmentQuerySchema(Schema):
    business_type = fields.String(
        required=False, validate=validate.OneOf(_ATTACHMENT_TYPES)
    )
    business_id = fields.Integer(required=False, validate=validate.Range(min=1))

    @validates_schema
    def validate_business_filter(self, data: dict, **_kwargs) -> None:
        if "business_id" in data and "business_type" not in data:
            raise ValidationError("按业务记录查询时必须提供业务类型")


class AttachmentUploadSchema(Schema):
    business_type = fields.String(
        required=True, validate=validate.OneOf(_ATTACHMENT_TYPES)
    )
    business_id = fields.Integer(
        required=False, allow_none=True, validate=validate.Range(min=1)
    )
    document_type = fields.String(
        required=False, load_default="OTHER", validate=validate.OneOf(_DOCUMENT_TYPES)
    )

    @validates_schema
    def validate_business_link(self, data: dict, **_kwargs) -> None:
        business_type = data.get("business_type")
        business_id = data.get("business_id")
        evidence_types = {
            "USAGE_SIGN",
            "RETURN_HANDOVER",
            "RETURN_INSPECTION",
            "TRANSFER_RECEIPT",
        }
        if (
            business_type in {"REPAIR", "SCRAP"} | evidence_types
            and business_id is None
        ):
            raise ValidationError("业务履约附件必须关联业务记录")
        if (
            business_type not in {"REPAIR", "SCRAP"} | evidence_types
            and business_id is not None
        ):
            raise ValidationError("普通资产附件不能关联业务记录")
        document_type = data.get("document_type")
        if business_type == "REPAIR" and document_type not in {
            "REPAIR_PHOTO",
            "REPAIR_QUOTE",
            "REPAIR_INVOICE",
            "OTHER",
        }:
            raise ValidationError("维修附件用途无效")
        if business_type == "SCRAP" and document_type not in {
            "SCRAP_CERTIFICATE",
            "DISPOSAL_VOUCHER",
            "OTHER",
        }:
            raise ValidationError("报废附件用途无效")


class AttachmentVoidSchema(Schema):
    reason = fields.String(required=True, validate=validate.Length(min=2, max=500))
    version = fields.Integer(required=True, strict=True, validate=validate.Range(min=1))


class AttachmentCoverSchema(Schema):
    version = fields.Integer(required=True, strict=True, validate=validate.Range(min=1))


__all__ = [
    "AttachmentCoverSchema",
    "AttachmentQuerySchema",
    "AttachmentUploadSchema",
    "AttachmentVoidSchema",
]
