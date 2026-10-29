"""Independent asset information change request endpoints."""

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.common import Result
from app.schemas.asset_information_change import (
    InformationChangePageSchema,
    InformationChangeRequestSchema,
)
from app.security import current_user_id
from app.services import asset_information_change_service

bp = Blueprint("asset_information_changes", __name__, url_prefix="/api/v1")
_request_schema = InformationChangeRequestSchema()
_page_schema = InformationChangePageSchema()


@bp.post("/asset-information-change-requests")
@jwt_required()
def submit_change_request() -> dict:
    payload = _request_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        asset_information_change_service.submit(payload, current_user_id())
    ).to_dict()


@bp.get("/asset-information-change-requests")
@jwt_required()
def list_change_requests() -> dict:
    query = _page_schema.load(request.args.to_dict())
    return Result.success(
        asset_information_change_service.list_requests(
            current_user_id(),
            page=query["page"],
            size=query["size"],
            change_type=query.get("change_type"),
        )
    ).to_dict()


@bp.get("/asset-information-change-requests/<int:operation_request_id>")
@jwt_required()
def get_change_request(operation_request_id: int) -> dict:
    return Result.success(
        asset_information_change_service.get(operation_request_id, current_user_id())
    ).to_dict()


__all__ = ["bp"]
