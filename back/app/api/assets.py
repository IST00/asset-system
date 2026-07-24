"""Formal asset and audit read endpoints."""

from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.common import Result
from app.schemas import (
    BatchCompleteAssetDataRequestSchema,
    CompleteAssetDataRequestSchema,
)
from app.schemas.asset import AssetPageQuerySchema
from app.security import current_user_id
from app.services import asset_data_completion_service, asset_service

bp = Blueprint("assets", __name__, url_prefix="/api/v1")

_page_schema = AssetPageQuerySchema()
_complete_data_schema = CompleteAssetDataRequestSchema()
_batch_complete_data_schema = BatchCompleteAssetDataRequestSchema()


@bp.get("/assets")
@jwt_required()
def page() -> dict:
    query = _page_schema.load(request.args.to_dict())
    result = asset_service.page(
        actor_id=current_user_id(),
        page_index=query["page"],
        size=query["size"],
        asset_code=query.get("asset_code"),
        asset_name=query.get("asset_name"),
        serial_number=query.get("serial_number"),
        data_completeness=query.get("data_completeness"),
    )
    return Result.success(result.to_dict()).to_dict()


@bp.get("/assets/<int:asset_id>")
@jwt_required()
def detail(asset_id: int) -> dict:
    return Result.success(asset_service.get(asset_id, current_user_id())).to_dict()


@bp.post("/assets/<int:asset_id>/complete-data")
@jwt_required()
def complete_data(asset_id: int) -> dict:
    payload = _complete_data_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        asset_data_completion_service.complete_data(
            asset_id,
            payload,
            current_user_id(),
        )
    ).to_dict()


@bp.post("/assets/complete-data")
@jwt_required()
def complete_data_batch() -> dict:
    payload = _batch_complete_data_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        asset_data_completion_service.complete_data_batch(
            payload,
            current_user_id(),
        )
    ).to_dict()


@bp.get("/assets/<int:asset_id>/lifecycle")
@jwt_required()
def lifecycle(asset_id: int) -> dict:
    return Result.success(
        asset_service.lifecycle(asset_id, current_user_id())
    ).to_dict()


@bp.get("/audit-logs")
@jwt_required()
def audit_logs() -> dict:
    return Result.success(asset_service.audit_logs(current_user_id())).to_dict()


__all__ = ["bp"]
