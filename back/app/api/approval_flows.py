"""Approval-flow configuration endpoints."""

from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.common import Result
from app.schemas.approval_flow import (
    ApprovalFlowDefinitionSchema,
    ApprovalFlowVersionSchema,
    ConfirmApprovalFlowActionSchema,
    CreateApprovalFlowRequestSchema,
    SaveApprovalFlowDraftRequestSchema,
)
from app.security import current_user_id
from app.services import approval_flow_service

bp = Blueprint("approval_flows", __name__, url_prefix="/api/v1")

_create_schema = CreateApprovalFlowRequestSchema()
_draft_schema = SaveApprovalFlowDraftRequestSchema()
_definition_schema = ApprovalFlowDefinitionSchema()
_definitions_schema = ApprovalFlowDefinitionSchema(many=True)
_version_schema = ApprovalFlowVersionSchema()
_confirm_schema = ConfirmApprovalFlowActionSchema()


@bp.get("/approval-flows")
@jwt_required()
def list_flows() -> dict:
    data = approval_flow_service.list_definitions(current_user_id())
    return Result.success(_definitions_schema.dump(data)).to_dict()


@bp.get("/approval-flows/<int:flow_id>")
@jwt_required()
def get_flow(flow_id: int) -> dict:
    data = approval_flow_service.get_definition(flow_id, current_user_id())
    return Result.success(_definition_schema.dump(data)).to_dict()


@bp.post("/approval-flows")
@jwt_required()
def create_flow() -> dict:
    payload = _create_schema.load(request.get_json(silent=True) or {})
    data = approval_flow_service.create_definition(
        payload["operation_type"], payload["name"], current_user_id()
    )
    return Result.success(_definition_schema.dump(data)).to_dict()


@bp.post("/approval-flows/<int:flow_id>/drafts")
@jwt_required()
def save_draft(flow_id: int) -> dict:
    payload = _draft_schema.load(request.get_json(silent=True) or {})
    data = approval_flow_service.save_draft(flow_id, payload, current_user_id())
    return Result.success(_version_schema.dump(data)).to_dict()


@bp.post("/approval-flow-versions/<int:version_id>/publish")
@jwt_required()
def publish(version_id: int) -> dict:
    _confirm_schema.load(request.get_json(silent=True) or {})
    data = approval_flow_service.publish(version_id, current_user_id())
    return Result.success(_version_schema.dump(data)).to_dict()


@bp.post("/approval-flows/<int:flow_id>/disable")
@jwt_required()
def disable(flow_id: int) -> dict:
    _confirm_schema.load(request.get_json(silent=True) or {})
    data = approval_flow_service.set_enabled(flow_id, False, current_user_id())
    return Result.success(_definition_schema.dump(data)).to_dict()


@bp.post("/approval-flows/<int:flow_id>/enable")
@jwt_required()
def enable(flow_id: int) -> dict:
    _confirm_schema.load(request.get_json(silent=True) or {})
    data = approval_flow_service.set_enabled(flow_id, True, current_user_id())
    return Result.success(_definition_schema.dump(data)).to_dict()


__all__ = ["bp"]
