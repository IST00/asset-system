"""Approval-flow configuration request and response schemas."""

from marshmallow import Schema, fields, validate

from app.enums import AssigneeType, SignMode


class CreateApprovalFlowRequestSchema(Schema):
    operation_type = fields.String(
        required=True, validate=validate.Length(min=1, max=32)
    )
    name = fields.String(required=True, validate=validate.Length(min=1, max=128))


class ApprovalFlowAssigneeRequestSchema(Schema):
    assignee_type = fields.String(
        required=True,
        validate=validate.OneOf([item.value for item in AssigneeType]),
    )
    assignee_id = fields.Integer(
        required=True, strict=True, validate=validate.Range(min=1)
    )


class ApprovalFlowLayerRequestSchema(Schema):
    level_no = fields.Integer(
        required=True, strict=True, validate=validate.Range(min=1)
    )
    sign_mode = fields.String(
        required=True,
        validate=validate.OneOf([item.value for item in SignMode]),
    )
    allow_self_approval = fields.Boolean(load_default=False)
    assignees = fields.List(
        fields.Nested(ApprovalFlowAssigneeRequestSchema),
        required=True,
        validate=validate.Length(min=1),
    )


class SaveApprovalFlowDraftRequestSchema(Schema):
    layers = fields.List(
        fields.Nested(ApprovalFlowLayerRequestSchema),
        required=True,
        validate=validate.Length(min=1),
    )


class ConfirmApprovalFlowActionSchema(Schema):
    confirmed = fields.Boolean(required=True, validate=validate.Equal(True))


class ApprovalFlowAssigneeSchema(Schema):
    id = fields.Integer(required=True)
    assignee_type = fields.String(required=True)
    assignee_id = fields.Integer(required=True)


class ApprovalFlowLayerSchema(Schema):
    id = fields.Integer(required=True)
    level_no = fields.Integer(required=True)
    sign_mode = fields.String(required=True)
    allow_self_approval = fields.Boolean(required=True)
    assignees = fields.List(fields.Nested(ApprovalFlowAssigneeSchema), required=True)


class ApprovalFlowVersionSchema(Schema):
    id = fields.Integer(required=True)
    flow_definition_id = fields.Integer(required=True)
    version_no = fields.Integer(required=True)
    status = fields.String(required=True)
    published_at = fields.String(allow_none=True)
    published_by = fields.Integer(allow_none=True)
    layers = fields.List(fields.Nested(ApprovalFlowLayerSchema), required=True)


class ApprovalFlowDefinitionSchema(Schema):
    id = fields.Integer(required=True)
    operation_type = fields.String(required=True)
    name = fields.String(required=True)
    status = fields.String(required=True)
    version = fields.Integer(required=True)
    versions = fields.List(fields.Nested(ApprovalFlowVersionSchema), load_default=list)


__all__ = [
    "ApprovalFlowDefinitionSchema",
    "ApprovalFlowVersionSchema",
    "ConfirmApprovalFlowActionSchema",
    "CreateApprovalFlowRequestSchema",
    "SaveApprovalFlowDraftRequestSchema",
]
