"""Role and permission management endpoints."""

from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.common import Result
from app.schemas.rbac import (
    CreateRoleRequestSchema,
    DeleteRoleRequestSchema,
    UpdateRolePermissionsRequestSchema,
    UpdateRoleRequestSchema,
    UpdateUserRolesRequestSchema,
)
from app.security import current_user_id
from app.services import rbac_service

bp = Blueprint("rbac", __name__, url_prefix="/api/v1")

_create_role_schema = CreateRoleRequestSchema()
_delete_role_schema = DeleteRoleRequestSchema()
_update_permissions_schema = UpdateRolePermissionsRequestSchema()
_update_role_schema = UpdateRoleRequestSchema()
_update_user_roles_schema = UpdateUserRolesRequestSchema()


@bp.get("/roles")
@jwt_required()
def list_roles() -> dict:
    return Result.success(rbac_service.list_roles(current_user_id())).to_dict()


@bp.get("/permissions")
@jwt_required()
def list_permissions() -> dict:
    return Result.success(rbac_service.list_permissions(current_user_id())).to_dict()


@bp.post("/roles")
@jwt_required()
def create_role() -> dict:
    payload = _create_role_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        rbac_service.create_role(payload, current_user_id())
    ).to_dict()


@bp.get("/roles/<int:role_id>/delete-impact")
@jwt_required()
def role_delete_impact(role_id: int) -> dict:
    return Result.success(
        rbac_service.role_delete_impact(role_id, current_user_id())
    ).to_dict()


@bp.post("/roles/<int:role_id>/delete")
@jwt_required()
def delete_role(role_id: int) -> dict:
    payload = _delete_role_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        rbac_service.delete_role(role_id, payload, current_user_id())
    ).to_dict()


@bp.post("/roles/<int:role_id>/update")
@jwt_required()
def update_role(role_id: int) -> dict:
    payload = _update_role_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        rbac_service.update_role(role_id, payload, current_user_id())
    ).to_dict()


@bp.post("/roles/<int:role_id>/permissions/update")
@jwt_required()
def update_role_permissions(role_id: int) -> dict:
    payload = _update_permissions_schema.load(request.get_json(silent=True) or {})
    data = rbac_service.update_role_permissions(
        role_id, payload["permission_ids"], current_user_id(), payload.get("reason")
    )
    return Result.success(data).to_dict()


@bp.post("/users/<int:user_id>/roles/update")
@jwt_required()
def update_user_roles(user_id: int) -> dict:
    payload = _update_user_roles_schema.load(request.get_json(silent=True) or {})
    data = rbac_service.update_user_roles(
        user_id, payload["role_ids"], current_user_id(), payload.get("reason")
    )
    return Result.success(data).to_dict()


__all__ = ["bp"]
