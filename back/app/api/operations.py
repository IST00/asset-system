"""Common operation-request and approval-task endpoints."""

from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.common import Result
from app.schemas.operation import (
    ActionKeySchema,
    ApprovalOpinionSchema,
    ConfirmReasonSchema,
    OperationPageQuerySchema,
    ReasonSchema,
    RejectionSchema,
)
from app.security import current_user_id
from app.services import operation_service

bp = Blueprint("operations", __name__, url_prefix="/api/v1")
_page_schema = OperationPageQuerySchema()
_opinion_schema = ApprovalOpinionSchema()
_rejection_schema = RejectionSchema()
_reason_schema = ReasonSchema()
_confirm_reason_schema = ConfirmReasonSchema()
_action_key_schema = ActionKeySchema()


@bp.get("/operation-requests")
@jwt_required()
def list_requests() -> dict:
    query = _page_schema.load(request.args.to_dict())
    return Result.success(
        operation_service.list_requests(
            current_user_id(), page=query["page"], size=query["size"]
        )
    ).to_dict()


@bp.get("/operation-requests/<int:operation_request_id>")
@jwt_required()
def get_request(operation_request_id: int) -> dict:
    return Result.success(
        operation_service.get_request(operation_request_id, current_user_id())
    ).to_dict()


@bp.get("/approval-tasks/my")
@jwt_required()
def my_tasks() -> dict:
    return Result.success(operation_service.my_tasks(current_user_id())).to_dict()


@bp.post("/approval-tasks/<int:task_id>/approve")
@jwt_required()
def approve(task_id: int) -> dict:
    payload = _opinion_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        operation_service.approve_task(
            task_id,
            current_user_id(),
            payload.get("opinion"),
            payload.get("idempotency_key"),
        )
    ).to_dict()


@bp.post("/approval-tasks/<int:task_id>/reject")
@jwt_required()
def reject(task_id: int) -> dict:
    payload = _rejection_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        operation_service.reject_task(
            task_id,
            current_user_id(),
            payload["opinion"],
            payload.get("idempotency_key"),
        )
    ).to_dict()


@bp.post("/operation-requests/<int:operation_request_id>/withdraw")
@jwt_required()
def withdraw(operation_request_id: int) -> dict:
    payload = _reason_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        operation_service.withdraw_request(
            operation_request_id,
            current_user_id(),
            payload["reason"],
            payload.get("idempotency_key"),
        )
    ).to_dict()


@bp.post("/operation-requests/<int:operation_request_id>/retry")
@jwt_required()
def retry(operation_request_id: int) -> dict:
    payload = _action_key_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        operation_service.retry_request(
            operation_request_id,
            current_user_id(),
            payload.get("idempotency_key"),
        )
    ).to_dict()


@bp.post("/operation-requests/<int:operation_request_id>/terminate")
@jwt_required()
def terminate(operation_request_id: int) -> dict:
    payload = _confirm_reason_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        operation_service.terminate_request(
            operation_request_id,
            current_user_id(),
            payload["reason"],
            payload.get("idempotency_key"),
        )
    ).to_dict()


__all__ = ["bp"]
