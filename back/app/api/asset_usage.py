"""HTTP boundary for personal and public asset-usage requests."""

from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.common import Result
from app.schemas.asset_usage_return import (
    PersonalUsageCreateSchema,
    PublicUsageCreateSchema,
    UsageReturnPageQuerySchema,
)
from app.security import current_user_id
from app.services import asset_usage_service

bp = Blueprint(
    "asset_usage",
    __name__,
    url_prefix="/api/v1/asset-usage-requests",
)

_personal_schema = PersonalUsageCreateSchema()
_public_schema = PublicUsageCreateSchema()
_page_schema = UsageReturnPageQuerySchema()


@bp.post("/personal")
@jwt_required()
def submit_personal() -> dict:
    payload = _personal_schema.load(request.get_json(silent=True) or {})
    data = asset_usage_service.submit_personal(payload, current_user_id())
    return Result.success(data).to_dict()


@bp.post("/public")
@jwt_required()
def submit_public() -> dict:
    payload = _public_schema.load(request.get_json(silent=True) or {})
    data = asset_usage_service.submit_public(payload, current_user_id())
    return Result.success(data).to_dict()


@bp.get("")
@jwt_required()
def page() -> dict:
    query = _page_schema.load(request.args.to_dict())
    data = asset_usage_service.page(
        actor_id=current_user_id(),
        page_index=query["page"],
        size=query["size"],
    ).to_dict()
    return Result.success(data).to_dict()


@bp.get("/<int:operation_request_id>")
@jwt_required()
def get(operation_request_id: int) -> dict:
    data = asset_usage_service.get(operation_request_id, current_user_id())
    return Result.success(data).to_dict()
