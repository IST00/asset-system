"""POST /api/auth/register  and  POST /api/auth/login.

Blueprints load requests via marshmallow schemas and delegate to
`app.services.auth_service` — no direct model/db touch here.
"""

from __future__ import annotations

from flask import Blueprint, request
from flask_jwt_extended import get_jwt, jwt_required

from app.common import Result
from app.schemas import LoginRequestSchema
from app.services import auth_service

bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")

_login_schema = LoginRequestSchema()


@bp.post("/login")
def login() -> dict:
    payload = _login_schema.load(request.get_json(silent=True) or {})
    login_data = auth_service.login(
        username=payload["username"],
        password=payload["password"],
        ip_address=request.remote_addr or "unknown",
        user_agent=request.headers.get("User-Agent"),
    )
    return Result.success(login_data).to_dict()


@bp.post("/logout")
@jwt_required()
def logout() -> dict:
    claims = get_jwt()
    auth_service.logout(
        user_id=int(claims["sub"]),
        session_id=str(claims.get("sid") or ""),
    )
    return Result.success(None).to_dict()
