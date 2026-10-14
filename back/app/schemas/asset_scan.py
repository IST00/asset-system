"""Scanner lookup input."""

from marshmallow import Schema, fields, validate, validates_schema, ValidationError


class AssetScanLookupSchema(Schema):
    asset_code = fields.String(required=False, validate=validate.Length(min=1, max=191))
    rfid_tag = fields.String(required=False, validate=validate.Length(min=1, max=191))

    @validates_schema
    def require_one(self, data: dict, **_kwargs: object) -> None:
        if (data.get("asset_code") is None) == (data.get("rfid_tag") is None):
            raise ValidationError("请提供资产编码或 RFID 标签之一")


class AssetUsageCandidateLookupSchema(Schema):
    asset_code = fields.String(required=False, validate=validate.Length(min=1, max=191))
    rfid_tag = fields.String(required=False, validate=validate.Length(min=1, max=191))

    @validates_schema
    def require_one(self, data: dict, **_kwargs: object) -> None:
        if (data.get("asset_code") is None) == (data.get("rfid_tag") is None):
            raise ValidationError("请提供资产编码或 RFID 标签之一")


# The intent endpoint intentionally reuses the scanner's validated lookup shape.
AssetScanIntentLookupSchema = AssetScanLookupSchema
