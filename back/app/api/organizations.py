"""Organization hierarchy endpoints."""

from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.common import Result
from app.schemas.master_data import (
    CreateOrganizationRequestSchema,
    UpdateOrganizationRequestSchema,
)
from app.security import current_user_id
from app.services import organization_service

bp = Blueprint("organizations", __name__, url_prefix="/api/v1/organizations")

_create_schema = CreateOrganizationRequestSchema()
_update_schema = UpdateOrganizationRequestSchema()


@bp.get("/tree")
@jwt_required()
def tree() -> dict:
    return Result.success(organization_service.tree(current_user_id())).to_dict()


@bp.get("/<int:organization_id>")
@jwt_required()
def detail(organization_id: int) -> dict:
    return Result.success(
        organization_service.get(organization_id, current_user_id())
    ).to_dict()


@bp.post("")
@jwt_required()
def create() -> dict:
    payload = _create_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        organization_service.create(payload, current_user_id())
    ).to_dict()


@bp.post("/<int:organization_id>/update")
@jwt_required()
def update(organization_id: int) -> dict:
    payload = _update_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        organization_service.update(organization_id, payload, current_user_id())
    ).to_dict()


@bp.post("/<int:organization_id>/disable")
@jwt_required()
def disable(organization_id: int) -> dict:
    return Result.success(
        organization_service.set_enabled(organization_id, False, current_user_id())
    ).to_dict()


@bp.post("/<int:organization_id>/enable")
@jwt_required()
def enable(organization_id: int) -> dict:
    return Result.success(
        organization_service.set_enabled(organization_id, True, current_user_id())
    ).to_dict()


__all__ = ["bp"]
