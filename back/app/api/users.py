"""GET /api/users/me  (auth) and  GET /api/users  (ADMIN)."""

from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

from app.common import BusinessException, Result, ResultCode
from app.schemas import PageQuerySchema
from app.security import require_role
from app.services import user_service

bp = Blueprint("users", __name__, url_prefix="/api/users")

_page_schema = PageQuerySchema()


@bp.get("/me")
@jwt_required()
def me() -> dict:
    username = get_jwt_identity()
    return Result.success(user_service.get_current(username)).to_dict()


@bp.get("")
@jwt_required()
def page_users() -> dict:
    if not require_role("ADMIN", get_jwt()):
        raise BusinessException(result_code=ResultCode.FORBIDDEN)

    query = _page_schema.load(request.args.to_dict())
    result = user_service.page(page_index=query["page"], size=query["size"])
    return Result.success(result.to_dict()).to_dict()
