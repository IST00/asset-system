"""GET /api/users/me  (auth) and  GET /api/users  (ADMIN)."""

from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from app.common import Result
from app.schemas import PageQuerySchema
from app.security import current_user_id
from app.services import permission_service, user_service

bp = Blueprint("users", __name__, url_prefix="/api/v1/users")

_page_schema = PageQuerySchema()


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
