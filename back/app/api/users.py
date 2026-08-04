"""GET /api/users/me  (auth) and  GET /api/users  (ADMIN)."""

from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import get_jwt, jwt_required

from app.common import Result
from app.schemas import ChangePasswordRequestSchema, PageQuerySchema
from app.schemas.user import UserPreferenceUpdateSchema
from app.security import current_user_id
from app.services import (
    permission_service,
    security_service,
    user_preference_service,
    user_service,
)

bp = Blueprint("users", __name__, url_prefix="/api/v1/users")

_page_schema = PageQuerySchema()
_change_password_schema = ChangePasswordRequestSchema()
_preference_schema = UserPreferenceUpdateSchema()


@bp.get("/me")
@jwt_required()
def me() -> dict:
    return Result.success(user_service.get_current(current_user_id())).to_dict()


@bp.get("")
@jwt_required()
def page_users() -> dict:
    permission_service.require_permission(current_user_id(), "system:user:view")

    query = _page_schema.load(request.args.to_dict())
    result = user_service.page(page_index=query["page"], size=query["size"])
    return Result.success(result.to_dict()).to_dict()


@bp.post("/me/password/update")
@jwt_required()
def update_my_password() -> dict:
    payload = _change_password_schema.load(request.get_json(silent=True) or {})
    result = user_service.change_password(
        current_user_id(),
        payload["current_password"],
        payload["new_password"],
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
    )
    return Result.success(result).to_dict()


@bp.get("/me/preferences")
@jwt_required()
def my_preferences() -> dict:
    return Result.success(user_preference_service.get(current_user_id())).to_dict()


@bp.post("/me/preferences/update")
@jwt_required()
def update_my_preferences() -> dict:
    payload = _preference_schema.load(request.get_json(silent=True) or {})
    return Result.success(
        user_preference_service.update(current_user_id(), payload)
    ).to_dict()


@bp.get("/me/sessions")
@jwt_required()
def my_sessions() -> dict:
    current_session_id = str(get_jwt().get("sid") or "") or None
    return Result.success(
        security_service.list_sessions(current_user_id(), current_session_id)
    ).to_dict()


@bp.post("/me/sessions/<string:session_id>/revoke")
@jwt_required()
def revoke_my_session(session_id: str) -> dict:
    current_session_id = str(get_jwt().get("sid") or "") or None
    return Result.success(
        security_service.revoke_user_session(
            current_user_id(), session_id, current_session_id
        )
    ).to_dict()
