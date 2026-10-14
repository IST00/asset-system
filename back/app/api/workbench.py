"""Employee task-center endpoints."""

from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.common import Result
from app.schemas.workbench import WorkbenchPageQuerySchema
from app.security import current_user_id
from app.services import workbench_service

bp = Blueprint("workbench", __name__, url_prefix="/api/v1/workbench")
_query_schema = WorkbenchPageQuerySchema()


def _query() -> dict:
    return _query_schema.load(request.args.to_dict())


@bp.get("/summary")
@jwt_required()
def summary() -> dict:
    return Result.success(workbench_service.summary(current_user_id())).to_dict()


@bp.get("/my-requests")
@jwt_required()
def my_requests() -> dict:
    return Result.success(
        workbench_service.my_requests(current_user_id(), _query())
    ).to_dict()


@bp.get("/assigned-to-me")
@jwt_required()
def assigned_to_me() -> dict:
    return Result.success(
        workbench_service.assigned_to_me(current_user_id(), _query())
    ).to_dict()


@bp.get("/pending-sign")
@jwt_required()
def pending_sign() -> dict:
    return Result.success(
        workbench_service.pending_sign(current_user_id(), _query())
    ).to_dict()


@bp.get("/pending-return")
@jwt_required()
def pending_return() -> dict:
    return Result.success(
        workbench_service.pending_return(current_user_id(), _query())
    ).to_dict()


@bp.get("/my-assets")
@jwt_required()
def my_assets() -> dict:
    return Result.success(
        workbench_service.my_assets(current_user_id(), _query())
    ).to_dict()


@bp.get("/my-borrowed")
@jwt_required()
def my_borrowed() -> dict:
    return Result.success(
        workbench_service.my_borrowed(current_user_id(), _query())
    ).to_dict()


@bp.get("/received-handovers")
@jwt_required()
def received_handovers() -> dict:
    return Result.success(
        workbench_service.received_handovers(current_user_id(), _query())
    ).to_dict()


@bp.get("/requests/<int:operation_request_id>")
@jwt_required()
def request_detail(operation_request_id: int) -> dict:
    return Result.success(
        workbench_service.request_detail(operation_request_id, current_user_id())
    ).to_dict()
