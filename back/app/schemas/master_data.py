"""Master-data request schemas."""

from marshmallow import Schema, fields, validate


class CreateOrganizationRequestSchema(Schema):
    code = fields.String(required=True, validate=validate.Length(min=1, max=64))
    name = fields.String(required=True, validate=validate.Length(min=1, max=128))
    parent_id = fields.Integer(required=False, allow_none=True, strict=True)


class UpdateOrganizationRequestSchema(Schema):
    name = fields.String(required=True, validate=validate.Length(min=1, max=128))
    parent_id = fields.Integer(required=False, allow_none=True, strict=True)
    version = fields.Integer(required=True, strict=True, validate=validate.Range(min=1))


class CreateReferenceDataRequestSchema(Schema):
    code = fields.String(required=True, validate=validate.Length(min=1, max=64))
    name = fields.String(required=True, validate=validate.Length(min=1, max=128))


class CreateLocationRequestSchema(CreateReferenceDataRequestSchema):
    parent_id = fields.Integer(required=False, allow_none=True, strict=True)
    is_selectable = fields.Boolean(load_default=True)


class CreateAssetCategoryRequestSchema(CreateReferenceDataRequestSchema):
    parent_id = fields.Integer(required=False, allow_none=True, strict=True)
    service_life_months = fields.Integer(
        required=True, strict=True, validate=validate.Range(min=1, max=1200)
    )
    default_unit_id = fields.Integer(required=True, strict=True)


class UpdateReferenceDataRequestSchema(Schema):
    name = fields.String(required=True, validate=validate.Length(min=1, max=128))
    version = fields.Integer(required=True, strict=True, validate=validate.Range(min=1))


class UpdateLocationRequestSchema(UpdateReferenceDataRequestSchema):
    parent_id = fields.Integer(required=False, allow_none=True, strict=True)
    is_selectable = fields.Boolean(required=True)


class UpdateAssetCategoryRequestSchema(UpdateReferenceDataRequestSchema):
    parent_id = fields.Integer(required=False, allow_none=True, strict=True)
    service_life_months = fields.Integer(
        required=True, strict=True, validate=validate.Range(min=1, max=1200)
    )
    default_unit_id = fields.Integer(required=True, strict=True)


__all__ = [
    "CreateAssetCategoryRequestSchema",
    "CreateLocationRequestSchema",
    "CreateOrganizationRequestSchema",
    "CreateReferenceDataRequestSchema",
    "UpdateAssetCategoryRequestSchema",
    "UpdateLocationRequestSchema",
    "UpdateOrganizationRequestSchema",
    "UpdateReferenceDataRequestSchema",
]
