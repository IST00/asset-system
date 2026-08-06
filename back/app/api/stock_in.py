"""Stock-in application endpoints."""

from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.common import Result
from app.schemas.stock_in import (
    ApprovalDecisionRequestSchema,
    CreateStockInRequestSchema,
    RejectStockInRequestSchema,
    ResubmitStockInRequestSchema,
    StockInPageQuerySchema,
)
from app.schemas.operation import ReasonSchema
from app.security import current_user_id
from app.services import stock_in_service

bp = Blueprint("stock_in", __name__, url_prefix="/api/v1/stock-in-requests")

_create_schema = CreateStockInRequestSchema()
_decision_schema = ApprovalDecisionRequestSchema()
_reject_schema = RejectStockInRequestSchema()
_resubmit_schema = ResubmitStockInRequestSchema()
_page_schema = StockInPageQuerySchema()
_reason_schema = ReasonSchema()


@bp.get("")
@jwt_required()
def page() -> dict:
    query = _page_schema.load(request.args.to_dict())
    result = stock_in_service.page(
        actor_id=current_user_id(),
        page_index=query["page"],
        size=query["size"],
        request_no=query.get("request_no"),
        approval_status=query.get("approval_status"),
        execution_status=query.get("execution_status"),
    )
    return Result.success(result.to_dict()).to_dict()


@bp.post("")
@jwt_required()
def submit() -> dict:
    payload = _create_schema.load(request.get_json(silent=True) or {})
    return Result.success(stock_in_service.submit(payload, current_user_id())).to_dict()


@bp.post("/<int:operation_request_id>/resubmit")
@jwt_required()
def resubmit(operation_request_id: int) -> dict:
    payload = _resubmit_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        stock_in_service.resubmit(operation_request_id, payload, current_user_id())
    ).to_dict()


@bp.get("/<int:operation_request_id>")
@jwt_required()
def detail(operation_request_id: int) -> dict:
    return Result.success(
        stock_in_service.get(operation_request_id, current_user_id())
    ).to_dict()


@bp.post("/<int:operation_request_id>/approve")
@jwt_required()
def approve(operation_request_id: int) -> dict:
    payload = _decision_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        stock_in_service.approve(
            operation_request_id, payload.get("opinion"), current_user_id()
        )
    ).to_dict()


@bp.post("/<int:operation_request_id>/reject")
@jwt_required()
def reject(operation_request_id: int) -> dict:
    payload = _reject_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        stock_in_service.reject(
            operation_request_id, payload["opinion"], current_user_id()
        )
    ).to_dict()


@bp.post("/<int:operation_request_id>/withdraw")
@jwt_required()
def withdraw(operation_request_id: int) -> dict:
    payload = _reason_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        stock_in_service.withdraw(
            operation_request_id, current_user_id(), payload["reason"]
        )
    ).to_dict()


@bp.post("/<int:operation_request_id>/retry")
@jwt_required()
def retry(operation_request_id: int) -> dict:
    return Result.success(
        stock_in_service.retry(operation_request_id, current_user_id())
    ).to_dict()


__all__ = ["bp"]
