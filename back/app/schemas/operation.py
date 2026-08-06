"""Common operation query and action schemas."""

from marshmallow import Schema, fields, validate


class OperationPageQuerySchema(Schema):
    page = fields.Integer(load_default=0, validate=validate.Range(min=0))
    size = fields.Integer(load_default=50, validate=validate.Range(min=1, max=100))


class ApprovalOpinionSchema(Schema):
    opinion = fields.String(
        required=False, allow_none=True, validate=validate.Length(max=2000)
    )
    idempotency_key = fields.String(
        required=False, allow_none=True, validate=validate.Length(min=1, max=191)
    )


class RejectionSchema(Schema):
    opinion = fields.String(required=True, validate=validate.Length(min=1, max=2000))
    idempotency_key = fields.String(
        required=False, allow_none=True, validate=validate.Length(min=1, max=191)
    )


class ReasonSchema(Schema):
    reason = fields.String(required=True, validate=validate.Length(min=1, max=2000))
    idempotency_key = fields.String(
        required=False, allow_none=True, validate=validate.Length(min=1, max=191)
    )


class ConfirmReasonSchema(ReasonSchema):
    confirmed = fields.Boolean(required=True, validate=validate.Equal(True))


class ActionKeySchema(Schema):
    idempotency_key = fields.String(
        required=False, allow_none=True, validate=validate.Length(min=1, max=191)
    )


class ApprovalTransferSchema(Schema):
    to_approver_id = fields.Integer(
        required=True, strict=True, validate=validate.Range(min=1)
    )
    task_version = fields.Integer(
        required=True, strict=True, validate=validate.Range(min=1)
    )
    reason = fields.String(required=True, validate=validate.Length(min=2, max=500))


class ApprovalReminderSchema(Schema):
    reason = fields.String(required=True, validate=validate.Length(min=2, max=500))


class OperationResponseSchema(Schema):
    data = fields.Dict(required=True)


__all__ = [
    "ApprovalOpinionSchema",
    "ActionKeySchema",
    "ConfirmReasonSchema",
    "OperationPageQuerySchema",
    "ReasonSchema",
    "RejectionSchema",
]
